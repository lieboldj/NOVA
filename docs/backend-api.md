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
4. Review one complete reply in the editable field table. Submit `POST /messages/{id}/approve-all`
   with a JSON list such as `[{"proposal_id":"...","value":"2028-12-31","action":"approve","version":1}]`.
   Include exactly one decision for every pending proposal in that reply; action is `approve` or `reject`.
   Edited approval values are validated, then the entire batch commits in one transaction, with one field
   audit per decision. The reply becomes reviewed and case completion runs once. A rejected field retains
   its accepted value. Any invalid value, stale version/field revision or wrong membership rejects the
   whole batch. `version` is optional for integration compatibility; the UI always sends it to detect edits.
   No-proposal replies can be reviewed with an empty list. Legacy per-proposal endpoints remain available.
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
An `evaluated` message has extracted value proposals, including unchanged confirmations.
`needs_review` means no supported candidates were produced. Every message remains a review item:
`GET /cases/{id}/messages` includes its complete original body and all attachment metadata, even when
no proposal cites that input. Original attachments remain available through protected downloads.
After checking the full reply and every attachment, submit the bulk review above. Other replies are
reviewed independently; the case cannot close until every reply and proposal is reviewed. The legacy
`POST /messages/{id}/review-complete` is also available once that reply has no pending proposals.
Automation cannot approve supplier data or complete a review. When incomplete-answer automation is enabled,
it can request unresolved answers while received values still await human review.

## Cases, reminders and partial replies

Common case states are `open`, `email_review`, `awaiting_reply`, `processing_reply`, `data_review`, `closed`,
`paused`, and `escalated`. Automation calls `POST /automation/tick` periodically. It returns counts for
`drafted`, `closed`, `escalated`, and `skipped`.

The backend filters outstanding editable fields and drafts a request for their references. Each draft has
a `requested_fields` snapshot recording what was asked. Extraction considers all fields belonging to that
case so that unsolicited answers and confirmations of already accepted values are also reviewable.
Other cases' fields cannot be proposed. All field context and evidence still pass through anonymization
before remote evaluation. An extracted value equal to its prior value is retained as a pending confirmation;
the human approval and validation rules also apply to these confirmations. Content without a supported
candidate remains visible in the complete reply and attachments. After full review, the next scheduled
check drafts a follow-up only for unresolved fields.

The response deadline begins when an email is sent/simulated, not when a draft is created or approved.
Incoming replies pause the deadline and supersede unsent drafts. A missing reply produces a reminder draft,
which is automatically approved when `AUTO_SEND_FOLLOWUPS=true` (default). Follow-ups after review use
that same policy; initial `request` drafts always remain pending for human approval. Automated sends wait
`AUTO_SEND_DELAY_MINUTES` (default 2, nonnegative) using `Job.available_at`. The audit actor is `automation`
and action is `email.auto_approved`, including the version and earliest send time. Editing increments the
version, clears approval and requires a new human decision; rejection or superseding invalidates the send.
The worker checks version, digest and case revision at dispatch. Save edits before dispatch starts;
unsaved browser text cannot stop delivery. Turning the flag off also cancels queued automated sends.
The default maximum is two sent reminders before escalation.

`AUTO_FOLLOWUP_ENABLED=true` additionally permits bounded incomplete-answer follow-ups during data review;
these also require `AUTO_SEND_FOLLOWUPS=true` and use the same delay. Their default cap is three rounds.
All automated email templates include the AI disclosure below the team sign-off.

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
before creating an email per article case. Initial requests are pending; follow-ups follow the configured automatic approval policy. Changed cases return `409` and require a new preview;
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
