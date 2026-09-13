# NOVA supplier portal

NOVA requests missing supplier information by email, evaluates replies and PDF attachments, and proposes
updates to supplier records. **A reviewer must approve each email before sending and each data change
before it becomes accepted supplier data.** The React control center is connected to the backend for
case review, versioned email and data approvals, replies, attachments, and operations.

**Supplier review** includes every received email in full, all its attachments, and extracted values
labelled as new, changed, or unchanged confirmations. Additional information without an extracted value
remains visible. After deciding a reply's proposals, the reviewer completes that reply's review explicitly;
case closure and follow-up drafting wait until every received reply has been reviewed.

## Google Cloud demo

NOVA is deployed at **https://nova-bnw6dmyvva-ey.a.run.app** with a clean database.
n8n runs at **https://nova-n8n-bnw6dmyvva-ey.a.run.app**. Login details are kept privately in the
operator's `.data/cloud/access.txt`. See [deployment, verification, test data and operations](docs/cloud-deployment.md).
The cloud demo uses `devstar4415@gcplab.me` for both sides of a test email exchange; NOVA excludes its
own outgoing requests from reply ingestion. The supplier test address remains configurable.

## Run locally

Requires Python 3.12+ and `uv`. PostgreSQL via Docker Compose is recommended for multiple processes.

```bash
uv sync
uv run python scripts/init_local.py
docker compose up -d --build api worker
```

Open **http://localhost:8000/** for the portal and **http://localhost:8000/docs** for API documentation.
Sign in with the local `NOVA_REVIEWER_TOKEN` access key from `.env`. Browser sign-in creates an HttpOnly
session; no credentials are embedded in the frontend build. See [frontend setup and workflow](docs/frontend-integration.md)
for development on port 5173, browser tests, and the approval contract. The API listens on localhost only.
`init_local.py` adds missing reviewer and automation credentials to the existing `.env` without displaying
or replacing existing credentials. `.env` is excluded from Git and Docker builds. `config/example.env`
documents supported settings and contains no credentials.

For lightweight, single-worker development with SQLite, run these in separate terminals:

```bash
uv run uvicorn nova.api:app --host 127.0.0.1 --port 8000
uv run python -m nova.worker
```

SQLite initializes its schema automatically. PostgreSQL uses `uv run alembic upgrade head`; Compose runs
that migration before starting the API and worker. Use PostgreSQL for concurrent workers and reviewers.

### Current defaults

- `MAIL_MODE=simulation`: approved messages are captured as `simulated` drafts; nothing is sent externally.
- `AI_MODE=gemini`, `ANONYMIZER_MODE=anymize`: missing Anymize access pauses processing. It never sends raw
  supplier content to Gemini as a fallback.
- `GEMINI_API_KEY` comes from local configuration. The default model is `gemini-3.8-flash`, verified with a
  fictional extraction request. The API rejected Gemini 2.5 Flash for this account.
- Set both `AI_MODE=fixture` and `ANONYMIZER_MODE=fixture` for an isolated, offline demonstration. This mode
  extracts explicit `ROW_ID=value` lines and is **not** a real anonymizer or AI evaluation. A remote model
  cannot run with fixture anonymization.
- Default response deadline: seven days after a successful or simulated send. Two approved reminders are
  allowed before escalation. Deadlines are stored as UTC timestamps in PostgreSQL.

After changing `.env`, restart the local processes, or recreate the containers:

```bash
docker compose up -d --force-recreate api worker
```

### Anymize integration

Set `ANYMIZE_API_KEY` in `.env` and keep `ANONYMIZER_MODE=anymize` and `AI_MODE=gemini`.
The existing reply worker anonymizes email bodies and extracted attachment text before evaluation;
textless PDF pages use Anymize's document endpoint. Proposed values and citations are restored in the
backend for human review. The frontend uses the normal reply and proposal endpoints.

After updating `.env`, recreate the API and worker containers using the command above. A container restart
alone does not load changed Compose environment values. Check authenticated `GET /configuration` for
`anonymizer_mode: "anymize"` and `anymize_configured: true`; the flag indicates a loaded key, not a live
provider connectivity test. Failed evaluation jobs can be retried through `POST /jobs/{id}/retry`.

Run the live check with fictional evidence only:

```bash
uv run python scripts/check_anymize.py --ocr --with-gemini
```

This checks text anonymization, JSON preservation, restoration, a generated PDF through the OCR endpoint,
and Gemini extraction from sanitized evidence. It uses provider credits. It does not read supplier files,
send email, or change accepted records. Omit the flags to check only Anymize text processing.

## API access and approvals

`NOVA_REVIEWER_TOKEN` is for the trusted human review client. `NOVA_AUTOMATION_TOKEN` is for n8n and can only
trigger checks and ingest replies. The automation credential cannot read original supplier records, approve
imports, approve emails, or approve changes. The Gemini model has no database, filesystem, email, or
de-anonymization tools. It receives a sanitized payload and returns structured proposals.

The initial implementation uses one configured reviewer identity (`NOVA_REVIEWER_NAME`). Before multiple
people use a deployed portal, replace this development token authentication with individual sign-in and
server-derived reviewer identities. Never embed the reviewer secret into a public frontend bundle.

Workflow records, incoming evidence, pending imports, proposals, and audit events are saved automatically.
They are separate from **accepted supplier records**, which change only through authenticated approval
endpoints. Reading an email or extracting a value does not approve it.

Use the local CLI to make authenticated calls without printing credentials:

```bash
uv run python scripts/nova_cli.py GET /configuration
uv run python scripts/nova_cli.py POST /imports --file Supplier_Submissions_TestSet.csv
uv run python scripts/nova_cli.py GET /imports/IMPORT_ID
uv run python scripts/nova_cli.py POST /imports/IMPORT_ID/approve --json '{"contacts":{}}'
uv run python scripts/nova_cli.py GET /cases
```

Replace `IMPORT_ID` with the returned identifier. Import approval can include contacts keyed by Supplier ID,
or a reviewer can approve a contact later using `POST /cases/{id}/contact/approve`. The input CSVs contain
no email addresses, so NOVA does not guess recipients. Once contacts are approved, n8n can trigger work.

| Operation | Endpoint | Access |
|---|---|---|
| Preview CSV import | `POST /imports` (multipart `file`) | Reviewer |
| Review/approve import | `GET /imports/{id}`, `POST /imports/{id}/approve` | Reviewer |
| View cases and fields | `GET /cases`, `GET /cases/{id}` | Reviewer |
| Approve contact | `POST /cases/{id}/contact/approve` | Reviewer |
| Check due cases | `POST /automation/tick` | Automation or reviewer |
| Create request/follow-up draft | `POST /cases/{id}/draft` | Reviewer |
| Read/edit drafts | `GET /drafts`, `PATCH /drafts/{id}` | Reviewer |
| Approve/reject email | `POST /drafts/{id}/approve` or `/reject` | Reviewer |
| Resolve uncertain send | `POST /drafts/{id}/reconcile` | Reviewer |
| Ingest supplier reply | `POST /cases/{id}/messages` (multipart) | Automation or reviewer |
| Review reply/evidence | `GET /messages/{id}`, `GET /documents/{id}` | Reviewer |
| Finish manual reply review | `POST /messages/{id}/review-complete` | Reviewer |
| Read/edit proposed changes | `GET /proposals`, `PATCH /proposals/{id}` | Reviewer |
| Approve/reject a change | `POST /proposals/{id}/approve` or `/reject` | Reviewer |
| Export accepted records | `GET /exports/submissions.csv` | Reviewer |
| Inspect jobs/retry failed evaluation | `GET /jobs`, `POST /jobs/{id}/retry` | Reviewer |
| View audit history | `GET /audit` | Reviewer |

See [frontend and integration handoff](docs/backend-api.md) for request shapes and state transitions.
See [the integration and Google Cloud deployment plan](docs/integration-deployment-plan.md) for remaining
work and required account access, and [the n8n workflow AI prompt](docs/n8n-workflow-ai-prompt.md) for workflow generation.

## n8n

Import [the workflow](integrations/n8n/check-pending-cases.json) into n8n. It calls NOVA every 15 minutes.
The workflow contains no credentials and is initially inactive.

1. In the HTTP Request node, select a Header Auth credential with header `Authorization` and value
   `Bearer YOUR_NOVA_AUTOMATION_TOKEN`. Enter the token locally in n8n's credentials UI.
2. Set the backend URL. `http://api:8000/automation/tick` works within the supplied Compose network.
3. Save, test, and publish the workflow. Timezone: `Europe/Berlin`.

An optional local n8n instance is available with `docker compose --profile n8n up -d n8n` at
http://localhost:5678. This optional local image uses `latest`; pin a tested version before shared deployment.
The schedule creates email drafts but never approves or sends them. The persistent NOVA worker consumes
jobs only after approval or receipt of a reply. A mailbox connector can post replies to the ingestion endpoint.

## Data and evidence

- Imports accept the exact v1 or v2 submission columns, up to 100,000 rows / 64 MiB. V2's Country, Workflow
  status and Last contact date columns are preserved. Existing Row IDs cannot be overwritten by import.
- CSV workflow/contact history does not establish a NOVA email approval or sent-message history. Imported
  cases start with a new NOVA request. Backend case state governs reminders; historical CSV columns remain
  unchanged except an approved field update marks that field's v2 Workflow status `Closed`.
- Follow-up and ground-truth files are evaluation resources. **Ground truth is never loaded by the agent.**
- Rules are read from `Data_Collection.csv`. The backend enforces explicit dropdown options, dates, years,
  concrete non-placeholder values, editable fields, and attachment ownership. The requirements contain
  ambiguous/conditional rules and typos; this is not a complete regulatory validation engine.
- Replies must match an approved supplier contact and reference an existing sent/simulated request.
  Prefix external message IDs with mailbox/provider identity to keep them globally unique.
- PDF and UTF-8 TXT attachments are supported, up to 10 MiB per message and 100 PDF pages. Textless PDF
  pages use Anymize OCR. Documents that exceed limits or fail parsing require manual review.
- Proposed values include the prior field revision, source message/document, page (when available), exact
  supporting quote, and validation errors. The backend rejects citations absent from the sanitized evidence.
- Originals live in `.data/documents` or the Compose document volume. Original files are only downloadable
  through reviewer-authenticated endpoints. No original filenames are included in agent input.

## Reliable processing

Jobs are persisted in PostgreSQL alongside the state transition that creates them. Workers claim jobs with
row locks and leases. Expired evaluation jobs can be recovered after a crash; completed work is fenced by a
claim token. Failed evaluations stay visible for explicit retry. Scheduled checks pick up overdue cases
after downtime and skip cases already awaiting approval or reply evaluation.

Email approval covers the exact recipient, subject, body, requested fields, and version. Editing invalidates
approval. New replies invalidate pending/approved drafts. The worker rechecks the approval digest and case
revision before transmission. Send timeouts are treated as uncertain; they are never blindly retried.
A reviewer must reconcile the outcome. Confirming `not_sent` requires a fresh approval before another attempt.

For SMTP delivery, configure `MAIL_MODE=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_SENDER`, and optionally
`SMTP_USERNAME` / `SMTP_PASSWORD`. STARTTLS is enabled by default. The default simulation path and its
approval gates are tested. Live fictional Gmail tests are documented in the cloud deployment guide.

## Verification

```bash
uv run pytest -q
uv run ruff check nova tests scripts migrations
uv run python scripts/check_gemini.py
```

The Gemini connectivity check sends only hard-coded fictional evidence. Tests never read `.env` credentials
and use fixture providers. To run against a disposable PostgreSQL database, set
`NOVA_TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/nova_test` before pytest.
**Tests recreate tables in that dedicated database.** PostgreSQL also enables the concurrent trigger,
approval, and worker regression test; SQLite skips that test.

## Deployment boundary

The Google Cloud demo uses Cloud SQL, private Cloud Storage and Secret Manager. The worker and n8n run
continuously on Cloud Run with minimum instances and always-allocated CPU; the public API can scale to zero.
The local Compose workflow remains supported. See the deployment guide for verified behavior, runtime IAM
limitations, costs and shutdown. A future task-driven worker is an alternative to the continuous deployment.

The final presentation is three minutes and the frontend is owned separately. Backend acceptance focuses
on a repeatable request → approval → reply/PDF → proposal → approval → CSV flow, plus partial replies and
reminders. Fixture simulation must remain visibly distinct from live provider processing.

## Gmail test accounts

The Gmail transport uses internal `devstar4415@gcplab.me` and supplier `devstar4418@gcplab.me`.
See [Gmail authorization and frontend/n8n integration](docs/gmail-setup.md).
Live access requires local OAuth setup; outgoing mail and accepted supplier data still require human approval.

## Interactive demonstration

Run `npm run demo`, open **http://localhost:8012/**, and sign in with **nova-demo**.
This loads fictional data and demonstrates email approval, PDF reply review, a follow-up, and separate
data approval without live providers or changes to the main database. See [the three-minute demo guide](docs/demo.md).

See [the demo and privacy walkthrough](docs/privacy-demo.md) for a short example and the exact anonymization boundaries.
