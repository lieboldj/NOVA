# NOVA integration and deployment plan

Status: planned work, not a completed cloud deployment. The two approval gates are mandatory throughout.

## Verified starting point

- FastAPI, PostgreSQL and a persistent worker run locally in Docker Compose.
- CSV staging/approval/export, email draft approval, data-change approval, reminder logic, and reply/PDF
  processing have regression coverage. All 22 tests passed against disposable PostgreSQL.
- The 52,546-row v2 submission dataset passed isolated import, approval, and export.
- `gemini-3.6-flash` passed a live structured extraction check with fictional evidence through the Gemini
  Developer API. Vertex AI is not configured. Emails use deterministic templates; Gemini evaluates evidence.
- End-to-end automated tests use fixture providers. Live Anymize/OCR, mailbox integration, n8n workflow
  execution, Google Cloud deployment, and individual reviewer sign-in remain unverified or unimplemented.

## 1. Connect and validate Anymize

Needed: approved account, available API credits, and a dedicated development API key configured locally as
`ANYMIZE_API_KEY`. Never send the key in chat or commit `.env`.

1. Confirm the account's current API contract and base URL. The implemented adapter follows the documented
   asynchronous text, OCR, status, and restoration endpoints. Check these against the approved account
   before sending supplier documents. [Anymize API documentation](https://developers.anymize.ai/)
2. Run contract checks with fictional company names, contact details, identifiers, native PDFs, scanned
   pages, and mixed documents. Check both identity removal and preservation of requested technical values.
3. Verify that sanitizing the JSON evidence bundle preserves its structure and opaque field/source IDs.
   If it does not, sanitize individual content blocks and reconstruct the structured payload inside NOVA.
4. Persist provider job IDs and processing checkpoints. Submit once and resume polling after restarts;
   divide long document processing into bounded steps rather than extending an in-memory polling loop.
5. Verify placeholder restoration and mapping lifetime across partial replies and later reminders. Restore
   values only in the trusted backend for review. Record source page/quote references throughout processing.
6. Add live contract tests for denied access, depleted credits, timeouts, malformed output, and retries.
   Errors must leave the case reviewable and must never cause a raw-data fallback to Gemini.

Acceptance: a fictional email plus PDF goes through real Anymize → Gemini → a pending proposal; model input
contains no seeded identifiers, evidence remains traceable, and accepted fields stay unchanged until approval.
Detection quality on real document layouts must be measured; removing known names alone is not proof that
all indirect identifiers have been removed.

## 2. Connect n8n

Needed: partner instance URL, installed n8n version, and editor access or a dedicated n8n API credential
stored outside Git. If no instance exists, provision one on a small Compute Engine VM with persistent
storage, HTTPS, a pinned image version, and separately managed n8n credentials.

1. Import `integrations/n8n/check-pending-cases.json`. Configure its HTTP Header Auth credential with the
   NOVA automation token, set the reachable API URL, and test it before publishing. The Schedule Trigger
   requires a published workflow and uses the workflow timezone. [Schedule documentation](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/)
2. Use `docs/n8n-workflow-ai-prompt.md` to generate the fuller integration. Keep a scheduled check workflow
   and a separate reply-ingestion workflow. Do not add approval, model, database, or email-send nodes.
3. Connect the chosen test mailbox. Normalize full email text, sender, subject, stable message identity,
   and binary attachments; route using the `[NOVA:CASE_UUID]` reference. Send one multipart request per
   message to the existing NOVA endpoint. Keep duplicate message IDs stable across retries.
4. Route invalid senders, missing case references, unsupported files, and rejected requests to an internal
   manual-review branch. Do not mark a mailbox item processed until NOVA acknowledges durable ingestion.
5. Configure retries for connection failures and transient server errors. Treat authentication, validation,
   and routing errors as actionable failures. Restrict execution-history retention for original email content.
6. Test repeated schedule triggers, duplicate replies, downtime recovery, multi-attachment replies, and
   failed ingestion. Verify automation credentials cannot approve or access accepted supplier records.

Acceptance: a real n8n execution creates a pending draft; another forwards a controlled test reply and PDF
exactly once logically despite retries. Approval is still performed only through NOVA's review API.

The HTTP Request node supports generic authentication and REST calls. No installed Anymize community node
is required because anonymization remains inside NOVA. [HTTP Request documentation](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/)

## 3. Prepare the backend for Google Cloud

Planning default: a dedicated demo project in Frankfurt (`europe-west3`), subject to the user's organization,
region requirements, service availability, and budget. Google Cloud hosting alone does not establish where
external Anymize or Gemini requests are processed.

| Component | Planned service | Work required |
|---|---|---|
| API | Cloud Run | Configure container port, authentication, readiness, and instance limits |
| Accepted data, workflow state, approvals | Cloud SQL PostgreSQL | Configure connection pool, migrations, backups, and service access |
| Original evidence and exports | Private Cloud Storage | Replace shared filesystem access with a storage adapter |
| Processing | Cloud Tasks → private Cloud Run worker | Replace the perpetual worker loop with bounded HTTP job handlers |
| Credentials | Secret Manager | Inject only the secrets required by each service |
| Container images | Artifact Registry | Build and tag immutable images using Git commit IDs |
| Reviewer access | Authenticated frontend server / identity integration | Resolve each reviewer's identity server-side |
| n8n | Existing partner instance, otherwise Compute Engine | Establish authenticated connectivity to NOVA |

Cloud Run supports Cloud SQL connections; use the same region and grant the runtime service account the
needed database access. Choose private networking or authenticated connector connectivity according to the
project's policies. [Cloud SQL connection guide](https://docs.cloud.google.com/sql/docs/postgres/connect-run)

Required application changes:

1. Add local and Cloud Storage implementations behind a shared document-storage interface. API and worker
   must read the same durable objects after restarts. Use object references rather than attachment bytes in
   queue payloads. Large imports should use an authenticated upload flow into private storage.
   [Cloud Storage uploads](https://docs.cloud.google.com/storage/docs/uploading-objects-from-memory)
2. Retain PostgreSQL job records as the source of truth. Add a dispatcher for queued records and a
   reconciliation scan for jobs committed before a failed Cloud Tasks enqueue. Include job ID and generation
   in each task; do not dispatch an arbitrary "next job" without a stable task/job association.
3. Add worker HTTP handlers that validate service identity, claim the intended job, and persist results before
   acknowledging completion. Split asynchronous Anymize submission, polling, OCR, and evaluation into bounded
   steps so task deadlines and leases remain valid. [Cloud Tasks with Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-tasks)
4. Preserve idempotency, version checks, approval digests, and uncertain-send reconciliation. Cloud Tasks can
   deliver duplicates; a retry must never create an extra email or apply a value twice.
   [Cloud Tasks execution behavior](https://docs.cloud.google.com/tasks/docs/common-pitfalls)
5. Keep runtime service accounts separate from reviewer identity. n8n must not receive reviewer or Gemini/
   Anymize credentials. An external n8n instance needs an agreed Google identity/federation path. Where both
   IAM and NOVA bearer authentication apply, use the Google ID token in `X-Serverless-Authorization` and the
   NOVA automation token in `Authorization`. Test this from the actual n8n host.
   [Service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)
6. Use Secret Manager for deployment configuration; do not copy local `.env` into images or infrastructure
   state. Implement individual reviewer authentication before a shared hosted portal accepts approvals.
   [Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)

Keep the verified Gemini Developer API integration initially. A Vertex AI adapter is a separate change:
verify the selected model's availability, project permissions, region, authentication, and response contract
before switching. Do not silently change the model or assume the existing API key grants Vertex access.

## 4. Deploy and rehearse

1. Prepare infrastructure-as-code and a resource/cost estimate using the supplied project, region, and budget.
   No billable resources have been created for this plan. The Google Cloud CLI is not installed locally yet.
2. Enable the required services and create storage, database, registry, runtime identities, task queues,
   secrets, and hosting resources. Use small bounded instance/queue concurrency initially; tune against
   actual Anymize limits and document sizes. Establish backup retention and resource ownership.
3. Build immutable images, run schema migrations as a deployment job, and deploy API and worker revisions.
   Preserve the previous revision for rollback; use backward-compatible database migrations.
4. Configure reviewer access and n8n connectivity. Keep mail simulated until approved-email delivery is
   verified against a controlled test mailbox. Provider choice and mailbox authorization are needed here.
5. Test the deployed loop: import → approve → n8n check → review email → send → receive PDF → extract →
   review changes → export. Also test duplicate tasks, late replies, partial replies, and restart recovery.
6. Prepare resettable fictional demo cases and separate simulation settings. The three-minute presentation
   can show both approval gates and a PDF-backed change; pre-seed overdue cases for a reminder scenario.
   Record a fallback demonstration and clearly label simulated supplier activity.

Acceptance: the frontend owner receives authenticated API access, working endpoint contracts, a deployed
test case, and evidence that both approval gates hold under retries. Actual mailbox and provider behavior
must be tested separately from fixture simulations.

## Inputs needed from the user

| Input | Needed for | Safe way to provide it |
|---|---|---|
| Anymize approval status and development API access | Live anonymization/OCR/restoration | Set `ANYMIZE_API_KEY` locally; share only that it is configured |
| n8n instance URL, version, editor/API access | Workflow import and testing | Share URL/version; enter credentials in n8n or local secret configuration |
| Google Cloud project ID, billing/partner-credit status | Resource plan and deployment | Share project ID and status; use local login or an approved deployment identity |
| Required region and approximate demo budget/lifetime | Resource selection and cost controls | Plain text is sufficient |
| Test mailbox provider/address and authorization method | Real reply ingestion and approved delivery | Share provider/address; connect OAuth or configure credentials privately |
| Reviewer identity provider or named demo reviewers | Authenticated approvals in the hosted portal | Share the sign-in requirement; no passwords needed |

Anymize and n8n account access are the immediate integration dependencies. Cloud changes can be developed
locally while project access is arranged. Domain and production supplier contacts can follow later.
