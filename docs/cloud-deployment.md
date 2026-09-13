# NOVA Google Cloud demo

Project: `aiwomen26ham-4415`. Region: Frankfurt, `europe-west3`.

- NOVA: https://nova-bnw6dmyvva-ey.a.run.app
- n8n: https://nova-n8n-bnw6dmyvva-ey.a.run.app

Access details are in ignored `.data/cloud/access.txt` — never commit or paste that file.
On first n8n login, skip the AI assistant setup (NOVA's own Anymize/Gemini integration covers that).

## Components

- Cloud Run `nova`: public frontend/API, 0–2 instances, 1 CPU / 512 MiB.
- Cloud Run `nova-worker`: private continuous worker, 1 instance, 1 CPU / 512 MiB.
- Cloud Run `nova-n8n`: 1 instance, 1 CPU / 1 GiB, pinned n8n 2.38.7.
- Cloud SQL `nova-db`: PostgreSQL 17, `db-g1-small`, single zone, 10 GiB SSD, daily backups.
  Separate `nova` and `n8n` databases; storage auto-growth disabled for the test budget.
- Private bucket `aiwomen26ham-4415-nova-evidence`: originals under opaque UUIDs, no public URLs.
- Secret Manager: DB credentials, reviewer/automation keys, Gmail OAuth, Anymize/Gemini keys,
  n8n credential-encryption key.
- Artifact Registry `europe-west3-docker.pkg.dev/aiwomen26ham-4415/nova`.

PostgreSQL job records (claim tokens, approval digests, uncertain-send state) stay the source of
truth — no in-memory queue. Worker and n8n run continuously (not scale-to-zero) so schedules and
recovery keep working between requests. Anymize receives originals; Gemini receives only NOVA's
sanitized evidence. No provider keys or raw messages are embedded in n8n workflows.

**IAM note:** the deployment account can create Cloud Run/SQL/storage/secret resources but not
project-wide IAM bindings, so it reuses the project's existing Editor-scoped compute service
account. Replace with dedicated least-privilege service accounts before any production use.

## Re-deploy

```bash
uv run python scripts/deploy_cloud.py identities
uv run python scripts/deploy_cloud.py database
uv run python scripts/deploy_cloud.py build
uv run python scripts/deploy_cloud.py deploy
uv run python scripts/setup_cloud_n8n.py
```

Reuses the existing generated cloud-secret file (doesn't rotate keys or overwrite databases).
The build excludes `.env`, `.data`, credentials, local DBs and supplier CSVs. Migrations run as a
one-off Cloud Run job before API/worker deploy. `setup_cloud_n8n.py` restores n8n owner access and
publishes the editor after its workflows are configured. State/URLs live in `.data/cloud/` — keep
an encrypted backup.

## Automation and test mailbox

n8n runs `check-pending-cases.json` (every 15 min) and `sync-gmail.json` (on Gmail push, plus a
15-min recovery check), both using only the automation credential. n8n's own credentials/workflows
persist in PostgreSQL with a fixed Secret Manager encryption key; execution retention is 7 days,
and NOVA's sync endpoint never returns message bodies.

Default sender/supplier: both `devstar4415@gcplab.me` (NOVA's own outgoing requests are excluded
from ingestion). To simulate a supplier, reply in Gmail keeping `[NOVA:...]` in the subject. To use
a different supplier mailbox, update `GMAIL_SUPPLIER` on API and worker, then re-approve that
contact — existing approved recipients are never changed silently.

## Gmail push delivery

Gmail INBOX watch → Pub/Sub `nova-gmail-inbox` → `/mail/gmail/push` → header-authenticated n8n
`nova-gmail-push` webhook → existing paginated sync. Originals stay in NOVA; n8n only gets a
wake-up signal. The receiver verifies Google's signature/audience/service-account/subscription and
acks only after a successful n8n sync; failed deliveries retry, duplicate Gmail IDs are a no-op.
`renew-gmail-watch.json` renews the watch daily; a 15-min recovery sync covers dropped
notifications. The `nova-gmail-push` identity has no data-access roles.

```bash
uv run python -m scripts.setup_gmail_push prepare
uv run python -m scripts.deploy_cloud build
uv run python -m scripts.setup_gmail_push deploy
uv run python -m scripts.setup_cloud_n8n
uv run python -m scripts.setup_gmail_push activate
uv run python -m scripts.verify_cloud
```

## Test data

- [`examples/cloud-demo.csv`](../examples/cloud-demo.csv) — one fictional supplier/article for a
  manual walkthrough (import → approve contact → send request → reply → review → export).
- [`examples/colleague-demo`](../examples/colleague-demo/README.md) — 20-supplier `DEMO20` fixture,
  loaded in the hosted demo, with simulated varied-format replies (`DEMO_AUTO_REPLY=true`).
- [`examples/colleague-demo/demo100`](../examples/colleague-demo/demo100/README.md) — 100-supplier
  `DEMO100` fixture (300 article cases, 6,600 fields) for scale testing; not auto-loaded.
- `scripts/check_cloud_workflow.py` — provisions an isolated `nova_smoke` DB and temporary
  services, sends one real fictional request + self-mail reply, checks live extraction, then
  tears down; never touches the main database.

## Cost and shutdown

Cloud SQL, the worker and n8n bill continuously even with no traffic — resource sizes are fixed
for this test but actual cost also includes storage, builds, provider usage and network; monitor
the billing console directly. To stop: pause n8n workflows and reconcile in-flight sends first,
then stop the continuous Cloud Run services and Cloud SQL. SQL deletion protection is on; deleting
databases/bucket/secrets needs an explicit separate decision.

## Policy: what runs automatically vs. what needs a reviewer

- **Initial `request` emails are always manually approved.** No exception.
- `AUTO_SEND_FOLLOWUPS=true` (default): reminders, post-review follow-ups, and incomplete-answer
  follow-ups (`AUTO_FOLLOWUP_ENABLED=true`, capped at 3 rounds/case) auto-approve and send after
  `AUTO_SEND_DELAY_MINUTES` (default 2), giving a reviewer a window to edit/cancel first. Every
  automated send is tagged `approved_by=automation` with its own `email.auto_approved` audit entry,
  and ends with an AI-disclosure line. Turning the flag off cancels queued auto-sends too.
- **Supplier data changes always need explicit reviewer approval** — via the batch
  `POST /messages/{id}/approve-all` screen, not per-field. Automation cannot approve data.
- Optional spelling-correction suggestions (from sanitized evidence only) are a review aid; a
  reviewer must still apply and approve them, nothing is auto-corrected.

## Verification log

- **2026-09-12 — initial deployment.** Real request/reply exchanged (`1a09754c4578ca57`/
  `1a09754d130ba2af`); live Anymize/Gemini produced 3 correct pending proposals incl. expiry
  `2028-12-31`. Auth boundaries confirmed live (401/403 on unauthenticated/anonymous access,
  CSRF-protected cookies). Both n8n workflows ran successfully, survived a service restart.
  46 backend + 4 browser tests passed. Repeat with `uv run python scripts/verify_cloud.py`.
- **2026-09-13 — Gmail push.** A real email reached a production n8n webhook in 3.8s with no
  manual sync; anonymous requests rejected. 48 tests passed. Check with
  `uv run python -m scripts.check_gmail_push`.
- **2026-09-13 — model update.** Switched to `GEMINI_MODEL=gemini-3.8-flash`; live extraction
  re-verified before the switch.
- **2026-09-13 — DEMO20 diversified + supplier 4418 simulation.** 20 suppliers now span 1–20
  outstanding fields each (231 total). `DEMO_AUTO_REPLY=true` generates labelled simulated replies
  (plain text, typos, TXT/PDF, scanned-PDF OCR) through real Anymize/Gemini — never a real email
  from the supplier account. Verified live: all 20 requests sent, 231 proposals + 41 optional
  spelling suggestions produced, all prior accepted data unchanged. 54 backend + 4 browser tests.
- **2026-09-13 — automatic incomplete-answer follow-ups.** `AUTO_FOLLOWUP_ENABLED=true` sends a
  follow-up only for fields still unresolved after evaluation (max 3 rounds/case). Verified against
  3 scenarios (partial, empty, invalid answers) — each got exactly the right follow-up and stopped
  after one round. 59 backend + 4 browser tests.
- **2026-09-13 — delayed auto-send + bulk review shipped**, plus the DEMO100 fixture (packaged for
  optional import/offline testing, not auto-loaded or auto-sent).
