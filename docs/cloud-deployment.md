# NOVA Google Cloud demo

Project: `aiwomen26ham-4415`. Region: Frankfurt, `europe-west3`.

- NOVA: https://nova-bnw6dmyvva-ey.a.run.app
- n8n: https://nova-n8n-bnw6dmyvva-ey.a.run.app

## Verified deployment — 12 September 2026

The app and worker run image `f810a924aebc`. The main NOVA database has zero cases; the local database
was not migrated. The separate cloud test sent request `1a09754c4578ca57` and reply `1a09754d130ba2af`
through the same Gmail mailbox. The request was correctly excluded from reply ingestion. Its PDF was
stored/read through private Cloud Storage, and live Anymize/Gemini processing produced three pending
proposals: unchanged material composition, new expiry date `2028-12-31`, and changed energy statement.
Accepted values were not changed. The temporary test API and worker were removed after verification.

Public NOVA browser login passed; unauthenticated record access returned 401, missing-CSRF writes returned
403, and cookies carried Secure, HttpOnly and SameSite=Strict. The worker's anonymous endpoint returned 403.
n8n owner login passed, anonymous workflow access returned 401, and both published n8n workflows completed
successful executions against the hosted NOVA API. Local verification: 46 backend tests and 4 browser tests
passed; the dedicated PostgreSQL concurrency test was skipped in the local SQLite run.
The n8n service was replaced with a fresh revision and both workflows executed successfully again,
confirming that the owner account, encrypted credential and schedules survived the restart.

Run `uv run python scripts/verify_cloud.py` to repeat deployment access/workflow checks. It executes the
two scheduler workflows but cannot approve or send an unapproved email. Detailed local evidence is in
`.data/cloud/verification.json` and `.data/cloud/smoke-result.json`.

The public NOVA service uses its existing shared reviewer login with a freshly generated secret,
HTTPS-only HttpOnly cookies, same-origin login, and CSRF protection. The worker service is private.
n8n's editor is exposed only after its owner account and strong password are configured.
Access details are saved to ignored `.data/cloud/access.txt`; never commit or paste that file publicly.
On first n8n login, skip the optional AI assistant using **Set up later in Settings**. NOVA's AI processing
already runs through its own Anymize/Gemini integration; no n8n assistant setup is needed.

## Components

- Cloud Run `nova`: public frontend/API, port 8000, 0–2 instances, 1 CPU / 512 MiB per instance.
- Cloud Run `nova-worker`: private continuous worker, 1 instance, 1 CPU / 512 MiB, instance-based billing.
- Cloud Run `nova-n8n`: 1 instance, 1 CPU / 1 GiB, instance-based billing, pinned n8n 2.38.7.
- Cloud SQL `nova-db`: PostgreSQL 17 Enterprise, `db-g1-small`, single zone, 10 GiB SSD, daily backups.
  Separate clean `nova` and `n8n` databases. Storage auto-growth is disabled for the test budget.
- Private bucket `aiwomen26ham-4415-nova-evidence`: original documents under opaque UUID object names.
  Both API and worker use the storage adapter; files survive instance replacement. No public object URLs.
- Secret Manager: regionally stored database credentials, reviewer/automation keys, Gmail OAuth,
  Anymize/Gemini keys, and the fixed n8n credential-encryption key.
- Artifact Registry `europe-west3-docker.pkg.dev/aiwomen26ham-4415/nova`: application and pinned n8n images.

The existing PostgreSQL jobs, claim tokens, approval digests, and uncertain-send handling remain the
source of truth. No in-memory queue replaces them. Cloud Run's always-allocated CPU and minimum instance
keep the continuous worker and n8n schedules running between web requests. A terminated evaluation is
recoverable after its lease expires; an interrupted send requires reconciliation rather than blind retry.
The worker and n8n are deliberately not configured to scale to zero.

Anymize is approved to receive originals. Gemini receives only the sanitized evidence selected by NOVA.
Google Cloud hosting stores original application records and documents; it is distinct from Gemini model
requests. No provider keys or raw messages are embedded in n8n workflows.

## IAM limitation of the lab project

The deployment account has permission to create Cloud Run/SQL/storage/secret resources but cannot modify
project-wide IAM bindings. The project already authorizes the default compute runtime service account
`1048492379133-compute@developer.gserviceaccount.com` with Editor, including SQL connection rights.
The demo uses that existing identity, with resource-scoped access to its secrets and evidence bucket.
This is broader than a production deployment should use. A project IAM administrator should replace it
with dedicated service accounts and least-privilege project roles before production use. The unsuccessful
attempt to prepare dedicated roles did not grant any new project-wide permissions.

## Re-deployment

The reusable script reads local provider credentials only when it generates the ignored cloud secret
file. Subsequent runs reuse it and do not rotate keys or overwrite existing databases. Secret references
are pinned to version 1; rotate explicitly by creating a new version and updating service references.

```bash
uv run python scripts/deploy_cloud.py identities
uv run python scripts/deploy_cloud.py database
uv run python scripts/deploy_cloud.py build
uv run python scripts/deploy_cloud.py deploy
uv run python scripts/setup_cloud_n8n.py
```

The initial one-time resources were provisioned with Google CLI: enabled Run, SQL Admin, Artifact Registry,
Secret Manager, Cloud Build and IAM APIs; created the Docker repository, private evidence bucket and SQL
instance. The script assumes those resources exist. The build uploads only the Docker context, excluding
`.env`, `.data`, credentials, local databases and supplier CSV datasets. Alembic migrations run as a one-off
Cloud Run job before the API and worker are deployed. The application starts without copying local data.

The `deploy` phase temporarily makes n8n private again while checking configuration. Running `setup_cloud_n8n.py`
restores owner access and publishes the editor after its workflows are configured. Setup state, URLs and
image references are in `.data/cloud/`; keep an encrypted backup of that operator directory.

## Automation and a single test mailbox

n8n runs `check-pending-cases.json` every 15 minutes and `sync-gmail.json` on authenticated Gmail push, with a 15-minute recovery check. Both call NOVA using
only its automation credential. The inbox workflow follows pagination. Approval endpoints remain available
only to the reviewer. n8n credentials/workflows/executions are persisted in PostgreSQL, with a fixed encryption
key in Secret Manager. Binary execution data uses database storage instead of the temporary filesystem.
Execution retention is seven days; no supplier message bodies are returned by NOVA's sync endpoint.

The default sender and test supplier are both `devstar4415@gcplab.me`. NOVA stamps its outgoing requests
and ignores those during inbox sync. To simulate a supplier, reply to the request in Gmail and retain the
`[NOVA:...]` subject reference. Gmail generates a new message ID; the reply is ingested once. To use another
supplier test mailbox, update `GMAIL_SUPPLIER` on both the NOVA API and worker, then approve that contact
on the case. Changing runtime configuration never silently changes already approved recipients.

## Test cases and extending NOVA

The main database starts empty. Download [the fictional demo CSV](../examples/cloud-demo.csv), use
**Import supplier CSV**, preview and approve it, and approve the intended test contact. Start a request
and explicitly approve its email. A sample reply is:

```text
CLOUD-DEMO-F1=80% recycled aluminium
CLOUD-DEMO-F2=2028-12-31
CLOUD-DEMO-F3=Renewable energy confirmed
The certificate expires on 31 December 2028.
```

This exercises an unsolicited unchanged confirmation, a missing date and a changed value. Add a PDF or
TXT attachment to test evidence storage. In **Supplier review**, inspect the complete input and proposals,
approve or reject values, then explicitly complete the reply review. For another import, use new Row IDs,
Supplier ID and NART; imports do not overwrite existing records.

`scripts/check_cloud_workflow.py` provisions a separate `nova_smoke` database and private temporary API/worker
services, sends one fictional request and one actual self-mail reply, and checks cloud storage and live
Anymize/Gemini extraction. It never seeds the main database. Its state file prevents duplicate sends on
retry. After success the temporary services are removed, and test evidence is retained in the isolated
database and private bucket. Inspect ambiguous sending outcomes before retrying.

Add new workflow data through reviewed CSV imports and `Data_Collection.csv` rules. Use Alembic migrations
for schema changes, tests for new workflow behavior, then build and deploy a new image. Do not edit running
containers or depend on their temporary filesystems. The existing offline demo remains available locally.

## Cost and shutdown

Cloud SQL, the continuous worker and n8n incur ongoing charges, even without web traffic. The earlier
€25–60 estimate assumed less continuous compute and is not a cap. Resource sizes/instance limits are fixed
for this test; actual costs also include storage, builds, external provider usage and network traffic.
Billing is enabled, but the remaining promotional-credit balance is not exposed by the project billing
status check. Monitor the project's billing console while the test runs.

To stop the demo, first pause n8n workflows and reconcile in-flight sends, then stop/remove the continuous
Cloud Run services and stop Cloud SQL. Preserve backups and secrets if the deployment will resume. SQL
deletion protection is enabled; deletion of databases, the bucket or secrets requires an explicit decision.


## Gmail push delivery

Gmail INBOX watch → regional Pub/Sub topic `nova-gmail-inbox` → authenticated
NOVA `/mail/gmail/push` → header-authenticated n8n `nova-gmail-push` webhook →
existing paginated Gmail sync. Originals stay in NOVA; n8n receives a wake-up signal.
The receiver verifies Google's signature, token audience, service-account email,
subscription and mailbox. It acknowledges only after n8n returns successful sync;
failed deliveries retry. Existing Gmail IDs prevent duplicate imports.

`renew-gmail-watch.json` renews the watch daily. Recovery sync runs every 15 minutes
because Gmail notifications can be dropped. The minute-by-minute trigger is removed.
Google documents renewal and delivery limits at
https://developers.google.com/workspace/gmail/api/guides/push.

Provision/update:
```bash
uv run python -m scripts.setup_gmail_push prepare
uv run python -m scripts.deploy_cloud build
uv run python -m scripts.setup_gmail_push deploy
uv run python -m scripts.setup_cloud_n8n
uv run python -m scripts.setup_gmail_push activate
uv run python -m scripts.verify_cloud
```

The dedicated `nova-gmail-push` identity has no data-access roles. Pub/Sub mints its push token using its existing Google-managed service agent role;
no additional project or service-account IAM binding is required.
Push configuration is recorded in ignored `.data/cloud/gmail-push.json` and preserved
by subsequent full deployments. Do not remove daily watch renewal while push is enabled.

See [the short demo and privacy walkthrough](privacy-demo.md) for the exact boundaries.
The operational database and evidence bucket retain originals; Gemini receives only
Anymize's sanitized extraction bundle, whose detection is not a universal guarantee.


Verified 2026-09-13: a fictional self-mail caused a production n8n webhook execution
containing its Gmail message ID within 3.8 seconds, without manual sync. The Pub/Sub
receiver returned 204; anonymous receiver and n8n webhook requests were rejected.
Backend suite: 48 passed, one PostgreSQL-specific concurrency check skipped locally.
`uv run python -m scripts.check_gmail_push` records the send before transmission and
reuses its private result file on retry, preventing accidental repeat test emails.


## Gemini model update — 2026-09-13

NOVA API and worker use `GEMINI_MODEL=gemini-3.8-flash` through Cloud Run environment
configuration. The existing Secret Manager API key is unchanged. Local defaults and
example configuration match. A live check with the deployed credentials passed Anymize
anonymization/restoration and structured extraction of `2028-12-31` from fictional,
sanitized evidence before the cloud switch. No supplier record or email was needed.
Official model ID: https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash.

## Diverse colleague demo — 2026-09-13

The existing 20 untouched `DEMO20` suppliers were updated using the scoped
`nova-demo-diversify` one-off Cloud Run job and `scripts/update_colleague_demo.py`.
The job reads the private `demo-fixtures/colleague-diverse-v2.csv` object from the evidence
bucket. It checks all 20 identities and refuses cases with sent/approved mail or replies,
updates fields transactionally, retains superseded drafts and creates fresh unapproved
requests. Other suppliers are outside its scope. Repeating the same update is idempotent.

There are 231 total fields, including 210 outstanding: one supplier at every count from
1 through 20. Local transaction/idempotence checks and live API counts/draft references
passed. All 231 prepared reply values pass the application validators. Industry-specific
questions are seeded explicitly; NOVA's industry filter does not infer category applicability.
