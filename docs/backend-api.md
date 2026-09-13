# NOVA frontend and integration handoff

Base URL: `http://localhost:8000`. Interactive schemas: `/docs`; OpenAPI: `/openapi.json`.
All endpoints need `Authorization: Bearer TOKEN`. Reviewer and automation tokens are distinct;
keep both server-side, never in browser JavaScript.

## Frontend sequence

1. `GET /cases`, `GET /cases/{id}` — accepted records, current revision, validation rules.
2. `GET /drafts?case_id=...` — `POST /drafts/{id}/approve` with `{"version":1}` queues delivery.
   Poll for `sent` / `simulated` / `superseded` / `uncertain`.
3. `GET /proposals?case_id=...` — evidence via `GET /messages/{id}` and `GET /documents/{id}`
   (PDF pages one-based).
4. Review a reply in one editable table, then `POST /messages/{id}/approve-all` with a decision
   per pending proposal: `[{"proposal_id":"...","value":"2028-12-31","action":"approve","version":1}]`.
   Commits as one transaction with one audit entry per field; any invalid/stale entry rejects the
   whole batch. `version` is optional but recommended (detects concurrent edits). Legacy
   per-proposal endpoints still exist.
5. `GET /exports/submissions.csv` — accepted values only.

`409` = stale/already-acted/blocked, reload and retry. `422` = validation failure. `401`/`403` = auth.

`PATCH /drafts/{id}` (with `{"version":1,...}`) creates a new pending version and clears approval.
Rejecting a draft pauses the case. A case can't get a new draft while another is active or a reply
is unreviewed.

## Reply ingestion (n8n or a mailbox adapter)

`POST /cases/{case_id}/messages`, multipart:

| Field | Meaning |
|---|---|
| `external_id` | Stable, globally unique message ID |
| `sender` | Must match the approved contact |
| `body` | Plain text |
| `attachments` | PDF/TXT parts, repeatable field name |

Subject carries `[NOVA:CASE_UUID]` for routing. Same `external_id` on retry returns the existing
message (`duplicate: true`); a duplicate ID under another case is rejected.

States: `queued → processing → evaluated|needs_review → reviewed` (or `failed`). Every message,
including ones with no matched proposal, stays reviewable via `GET /cases/{id}/messages`. The case
can't close until every reply is reviewed. Automation can ingest but never approve.

## Cases, reminders, partial replies

States: `open`, `email_review`, `awaiting_reply`, `processing_reply`, `data_review`, `closed`,
`paused`, `escalated`. `POST /automation/tick` (run periodically) returns
`{drafted, closed, escalated, skipped}`.

The deadline starts at send/simulate, pauses on reply, and a missed deadline drafts a reminder.
With `AUTO_SEND_FOLLOWUPS=true` (default), reminders and follow-ups auto-approve and send after
`AUTO_SEND_DELAY_MINUTES` (default 2) — **initial `request` drafts always need manual approval**.
Editing a queued draft clears approval and cancels the pending send; turning the flag off cancels
queued auto-sends too. Default cap: two reminders before escalation.
`AUTO_FOLLOWUP_ENABLED=true` additionally allows bounded incomplete-answer follow-ups (default cap:
3 rounds), same delay policy. All automated templates carry the AI disclosure line.

## Uncertain sends

`POST /drafts/{id}/reconcile` (reviewer-only) after checking the provider mailbox:

```json
{"version":1,"outcome":"not_sent","note":"Confirmed absent from provider delivery records"}
```
→ opens a new pending draft, no resend.

```json
{"version":1,"outcome":"sent","note":"...","provider_id":"provider-message-001","sent_at":"2026-09-12T10:00:00Z"}
```
→ restores tracking with the real send time, no additional send.

## Provider boundaries

Anymize receives original text/documents; known identifiers are replaced locally first. Gemini
receives only Anymize's sanitized JSON — never raw text, filenames, or Anymize's mapping/original
endpoints. It returns candidates with exact source citations and cannot send email, touch the
database, or accept changes; NOVA validates schema, field scope, citation, and rules before a
proposal is created.

`GET /configuration` reports `anonymizer_mode`, `anymize_configured`, `ai_mode`, `gemini_configured`
— these reflect loaded credentials, not a live health check. `GET /jobs` shows failed evaluations;
`POST /jobs/{id}/retry` requeues. Run `uv run python scripts/check_anymize.py --ocr --with-gemini`
for a live check; the fixture provider is offline-only and must never be presented as live AI.

## Gmail inbox and delivery

See [gmail-setup.md](gmail-setup.md#frontend-and-n8n-contract).

## Human-initiated questionnaire batches

`POST /processes/preview` with `{"command":"Send the MDF request to APAC automotive suppliers"}`
returns interpreted criteria, matching cases, blocking reasons, and a 30-minute `preview_token`
(no drafts/jobs created yet). `POST /processes/start` with `{"preview_token":"...","case_ids":[...]}`
(up to 500) creates one email per selected case — initial requests still need manual approval;
follow-ups use the normal auto-send policy. Stale selections return `409`; unpreviewed ones `422`.
Reviewer credentials only; automation cannot initiate.

The local command parser supports one region and/or industry (`and`), named suppliers, or
`all suppliers` — no external LLM, no disjunctions/exclusions (rejected explicitly rather than
ignored). Optional `Region`/`Industry` CSV columns (either v1 or v2 headers) enable this; they're
never inferred from supplier name or country.
