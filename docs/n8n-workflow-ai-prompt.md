# Prompt for the n8n workflow AI

Paste the following into n8n's workflow AI. It describes existing NOVA endpoints and keeps all approvals in
the backend. For an n8n instance outside the local Docker network, supply a reachable NOVA URL first.

```text
Build two n8n workflows for NOVA, an internal supplier information follow-up system.

NOVA already has a FastAPI backend, PostgreSQL, a background worker, and human review endpoints.
Your workflows orchestrate scheduled checks and forward incoming supplier replies. The backend owns
anonymization with Anymize, Gemini evaluation, deadlines, drafts, approval gates, delivery, and data updates.

MANDATORY BOUNDARIES
- Never send supplier emails from n8n in these workflows.
- Never approve emails or data changes, or call any /approve endpoint.
- Never connect directly to the supplier database or run SQL.
- Never send email content or attachments directly to an AI model.
- Do not add an AI Agent node. All model processing happens inside NOVA after sanitization.
- Store credentials in n8n's credential manager, not Code nodes or exported workflow JSON.
- Generate workflows inactive/unpublished. Do not execute mailbox actions during generation.

CONFIGURATION
- NOVA_BASE_URL is configurable. For n8n on NOVA's Docker Compose network, use http://api:8000.
  For a hosted n8n instance, require a reachable HTTPS backend URL; localhost will not reach my computer.
- Use an HTTP Header Auth credential named NOVA Automation:
  header name Authorization; header value Bearer <NOVA_AUTOMATION_TOKEN>.
  Leave the real credential for me to configure. Never request NOVA_REVIEWER_TOKEN.
- Timezone: Europe/Berlin.
- Email provider is not selected yet. Do not invent Gmail/Outlook credentials. Build the ingestion portion
  with an Execute Sub-workflow Trigger and documented input contract; explain where a mailbox trigger
  and full-message/attachment retrieval step will connect later.

WORKFLOW 1: NOVA - Check pending cases
1. Schedule Trigger: every 15 minutes, plus an alternative Manual Trigger for testing.
2. HTTP Request: POST {{NOVA_BASE_URL}}/automation/tick, with NOVA Automation authentication and no body.
3. Successful response example:
   {"drafted":1,"closed":0,"escalated":0,"skipped":2}
   Return these counts as the execution result. These are draft counts, NOT sent emails.
4. Connection failures, HTTP 429 and HTTP 5xx: retry at most three times with bounded delays.
   HTTP 401/403: credential/access failure. Other HTTP 4xx: manual inspection; do not retry indefinitely.
5. Make exhausted retries and non-retryable errors visible as failed executions with a concise reason.

WORKFLOW 2: NOVA - Ingest supplier reply
Expected input: mailbox/provider identifier, stable provider message ID, sender email, subject,
full plain-text body, and zero or more binary attachments. One input item represents one whole email.
1. Validate input. Prefer the full plain-text body; do not use a truncated mailbox preview/snippet.
2. Extract case_id from the subject reference [NOVA:UUID], preserving replies such as Re: [NOVA:UUID].
   If there is no reference, or multiple different references, stop for manual routing. Never guess.
3. Form external_id from mailbox identity + provider message ID. Keep it stable for every retry;
   never generate a new timestamp or random ID for the same email.
4. Send exactly ONE HTTP multipart/form-data request to:
   POST {{NOVA_BASE_URL}}/cases/{case_id}/messages
   with NOVA Automation authentication and these fields:
     external_id: stable identifier from step 3
     sender: supplier email address
     body: full plain-text email body
     attachments: each PDF/TXT as an actual binary file part under the repeated name attachments
   Forward all attachments together. Do not split one email into multiple ingestion requests, send
   base64 inside JSON, or silently drop unsupported/oversized files. NOVA supports PDF and UTF-8 TXT,
   up to 10 attachments and 10 MiB for the combined body and files. Route unsupported input for review.
5. Successful response, HTTP 201:
   {"id":"MESSAGE_UUID","status":"queued","duplicate":false}
   A retry can return duplicate:true and the existing message status. Treat this as success too.
   Ingestion success does NOT mean extraction completed or any data was approved.
6. HTTP 409 means routing/contact/state conflict and requires manual review. HTTP 413/422 means an
   input problem. Do not retry these blindly. Apply bounded retries only to transient failures.
7. Do not mark or move the provider email until NOVA acknowledges ingestion. Leave this mailbox-specific
   step as a documented connection point until a provider has been selected.

IMPLEMENTATION REQUIREMENTS
- Use current built-in n8n nodes; no unverified community packages.
- Keep binary data intact through validation and routing. If dynamic repeated multipart file parts need
  additional configuration, explain it; do not produce a workflow that only uploads the first file.
- On failure, report workflow name, step, execution/message reference, and status code. Do not send full
  email bodies, attachments, or credentials to an external notification channel.
- Explain how to limit retained execution data because supplier emails can contain identifying information.
- Add clear node labels and setup notes. Do not invent backend endpoints.
- If you can generate only one workflow at a time, generate Workflow 1 first, then Workflow 2.

Return the workflows plus credential/setup instructions and a short test checklist covering manual
triggering, duplicate replies, a PDF attachment, multiple attachments, missing case reference, sender
mismatch, and a temporary backend failure. Do not activate or publish until I configure and test them.
```
