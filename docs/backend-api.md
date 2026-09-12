# NOVA frontend and integration handoff

Base URL for local development: `http://localhost:8000`. Interactive schemas: `/docs`; OpenAPI: `/openapi.json`.
All business endpoints require `Authorization: Bearer TOKEN`. Reviewer and automation credentials are distinct.
Keep credentials in the trusted frontend server; do not ship them in browser JavaScript.

## Minimal frontend sequence

1. Load `GET /cases` and then `GET /cases/{id}`. Field records include their original CSV row, current revision,
   and configured validation rules. These are the accepted records.
2. Load `GET /drafts?case_id=...`. Show the complete recipient, subject, body, kind, status, and version.
   `POST /drafts/{id}/approve` with `{"version": 1}` approves that exact version and queues delivery.
   The request returns `approved`; poll the draft list for `sent`, `simulated`, `superseded`, or `uncertain`.
3. Load `GET /proposals?case_id=...`. Show `field_id`, `old_value`, `value`, evidence, validation errors,
   status, and version. Retrieve original evidence through `GET /messages/{message_id}` and
   `GET /documents/{document_id}`. PDF pages are one-based.
4. Approve each accepted change with `POST /proposals/{id}/approve`, body `{"version": 1}`. Reject a proposal
   through `/reject` with the same version body. Edits use `PATCH /proposals/{id}` with
   `{"version": 1, "value": "2028-12-31"}` and require approval of the returned new version.
5. Download `GET /exports/submissions.csv`. It contains accepted values only.

`409` means the record is stale, already acted upon, blocked, or inconsistent with the requested action.
Reload the current record and ask the reviewer to reconsider it. Never silently reapprove a newer version.
`422` reports validation failures. `401` / `403` indicate missing or insufficient credentials.

Email edits use `PATCH /drafts/{id}` with `{"version":1,"subject":"...","body":"..."}`. Editing returns a new
pending version and clears approval. Rejecting a draft pauses the case; a reviewer can create another draft
when ready. A case cannot get a new draft while another active draft or unreviewed reply exists.

## Reply ingestion from n8n or a mailbox adapter

`POST /cases/{case_id}/messages` accepts multipart form data:

| Field | Meaning |
|---|---|
| `external_id` | Stable, globally unique mailbox/provider message identifier |
| `sender` | Supplier email address; must match the approved contact |
| `body` | Plain text email body |
| `attachments` | Zero or more PDF/TXT file parts using this same field name |

The email subject includes `[NOVA:CASE_UUID]` for case routing. Supply the same `external_id` when retrying
ingestion. Repeated delivery returns the existing message identifier with `duplicate: true`. A duplicate ID
associated with another case is rejected. The first delivery returns `queued`; the worker evaluates it.

Example with the local development environment supplying the automation token:

```http
POST /cases/CASE_UUID/messages
Authorization: Bearer AUTOMATION_TOKEN
Content-Type: multipart/form-data; boundary=...

external_id = demo-mailbox:message-001
sender = supplier@example.com
body = The requested expiry date is in the attached certificate.
attachments = certificate.pdf
```

Processing states: `queued`, `processing`, `evaluated`, `needs_review`, `failed`, `reviewed`.
An `evaluated` message has change proposals. `needs_review` means no supported candidates were produced.
After reviewing a no-answer or failed reply, a reviewer can call `/messages/{id}/review-complete` to release
the case for a targeted follow-up. Pending proposals must be approved or rejected first.

## Cases, reminders and partial replies

Common case states are `open`, `email_review`, `awaiting_reply`, `processing_reply`, `data_review`, `closed`,
`paused`, and `escalated`. Automation calls `POST /automation/tick` periodically. It returns counts for
`drafted`, `closed`, `escalated`, and `skipped`.

The backend filters outstanding editable fields and drafts a request for their references. Each draft has
a `requested_fields` snapshot. A reply is evaluated against the most recent sent request's snapshot, so
unrequested model output cannot change unrelated fields. A partial reply produces proposals for supported
answers; after review, the next scheduled check drafts a follow-up only for unresolved fields.

The response deadline begins when an email is sent/simulated, not when a draft is created or approved.
Incoming replies pause the deadline and supersede unsent drafts. A missing reply produces a reminder draft,
which still requires approval. The default maximum is two sent reminders before escalation.

## Uncertain sending outcomes

`POST /drafts/{id}/reconcile` is reviewer-only. First inspect the provider mailbox/logs.

If confirmed not sent:

```json
{"version":1,"outcome":"not_sent","note":"Confirmed absent from provider delivery records"}
```

This creates a new pending draft version; it does not resend it.

If confirmed sent:

```json
{
  "version":1,
  "outcome":"sent",
  "note":"Confirmed in provider delivery records",
  "provider_id":"provider-message-001",
  "sent_at":"2026-09-12T10:00:00Z"
}
```

This restores tracking using the actual sending time. No additional send is performed.

## Provider boundaries

Anymize receives original free text and documents. NOVA first replaces known supplier identifiers locally,
then requires sanitized JSON from Anymize before Gemini can run. Company identifiers and actual CSV row IDs
are replaced with aliases in model input. Only sanitized fields and sources enter the model request.
Anymize's `original_text`, filename metadata, and mapping endpoints are not exposed to the model.

The model returns candidate field values with exact source citations; it cannot send email, accept changes,
or browse the database. NOVA checks the candidate schema, field scope, citations, validation rules, and
field revision. Values and evidence are restored for human review inside the trusted backend.

Live Anymize text anonymization, JSON preservation, restoration, PDF processing, and sanitized Gemini
extraction have passed checks with fictional evidence. The documented text API is used for a JSON evidence
bundle; if its response cannot preserve that structure, the job fails closed. These checks do not measure
identity detection across real supplier documents or scanned/mixed-page PDFs.

For frontend connection status, authenticated `GET /configuration` returns `anonymizer_mode`,
`anymize_configured`, `ai_mode`, and `gemini_configured`. Configured flags indicate loaded credentials,
not a live provider health check. Submit replies through the existing message endpoint and poll jobs and
proposals. Failed evaluations expose a safe error in `GET /jobs`; `POST /jobs/{id}/retry` queues a retry
after the provider issue is resolved. No Anymize credentials or direct provider calls belong in the browser.

Run `uv run python scripts/check_anymize.py --ocr --with-gemini` for the synthetic live check. The fixture
provider remains available only for repeatable offline testing and must not be presented as live AI.

## Three-minute presentation support

The frontend can show one fictional case with three requested fields, a pending email, and a partial reply
with a one-page PDF. Show both approvals and the resulting CSV change. Integration tests already exercise
this flow. They advance stored deadlines in disposable test databases to exercise reminders; no production
API bypasses the configured response deadlines or approval requirements.

## Gmail inbox and delivery

See [the Gmail integration contract](gmail-setup.md#frontend-and-n8n-contract) for connection status,
inbox reading, paginated n8n synchronization, and retry/reconciliation behavior.

## Human-initiated questionnaire batches

In **Start process**, internal reviewers can describe an audience, preview it, select article cases,
and prepare the corresponding MDF emails. For example:

> For suppliers who are in region APAC and are in automotive industry, send the MDF request.

`POST /processes/preview` accepts `{"command":"Send the MDF request to APAC automotive suppliers"}`.
It returns interpreted `criteria`, matching cases with recipients and outstanding MDF fields,
eligibility/blocking reasons, the number of cases missing required targeting metadata, and a signed
`preview_token` valid for 30 minutes. Previewing creates no drafts or jobs.

`POST /processes/start` accepts `{"preview_token":"...","case_ids":["..."]}`. Select any nonempty subset
of eligible cases from the preview, up to 500. The server locks and revalidates the complete selection
before creating a pending email per article case. Changed cases return `409` and require a new preview;
unpreviewed cases return `422`. Retries cannot duplicate active requests. Each case records a
`process.initiated` audit event with the human actor, original command, criteria, and draft ID.
Emails use the existing individual review, approval, and delivery endpoints. Both process endpoints
require reviewer credentials; automation credentials cannot initiate a human request.

This first version interprets commands locally using imported supplier names/IDs, region and industry
values, and the MDF questionnaire. It supports one region and one industry joined with `and`, multiple
named suppliers joined with `and`, and explicit `all suppliers`. Different criteria intersect.
It rejects unknown terms, exclusions, disjunctions, and other questionnaire types rather than ignoring
them. It does not require an external language model. Empty results and blocked cases remain visible.
Cases awaiting replies, with active drafts or unreviewed replies, or requiring individual restart
review cannot be started as part of a batch.

Supplier submissions CSVs may include optional `Region` and `Industry` columns alongside either v1
or v2 headers. These attributes are retained in approved field rows and CSV exports; no database
migration is needed. Matching ignores case and surrounding/repeated whitespace. Missing or conflicting
attributes within an article case exclude it from the corresponding filter. Region and industry are
not inferred from supplier names or country. Existing sample CSVs do not contain these attributes;
include them in new imports to use audience targeting. Imports retain the existing non-overwrite rule
for row IDs. This flow requests outstanding supplier-editable MDF fields from already imported cases;
it does not create questionnaire definitions or new suppliers.
