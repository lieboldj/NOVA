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
- Email provider is Gmail. NOVA internal: devstar4415@gcplab.me. Test supplier: devstar4418@gcplab.me.
  Gmail OAuth credentials stay in NOVA; n8n needs only the NOVA Automation credential.

WORKFLOW 1: NOVA - Check pending cases
1. Schedule Trigger: every 15 minutes, plus an alternative Manual Trigger for testing.
2. HTTP Request: POST {{NOVA_BASE_URL}}/automation/tick, with NOVA Automation authentication and no body.
3. Successful response example:
   {"drafted":1,"closed":0,"escalated":0,"skipped":2}
   Return these counts as the execution result. These are draft counts, NOT sent emails.
4. Connection failures, HTTP 429 and HTTP 5xx: retry at most three times with bounded delays.
   HTTP 401/403: credential/access failure. Other HTTP 4xx: manual inspection; do not retry indefinitely.
5. Make exhausted retries and non-retryable errors visible as failed executions with a concise reason.

WORKFLOW 2: NOVA - Sync Gmail supplier replies
1. Schedule Trigger every minute, plus an alternative Manual Trigger for testing.
2. HTTP Request POST {{NOVA_BASE_URL}}/automation/gmail/sync with NOVA Automation authentication.
   No request body. Set an appropriate timeout (120 seconds for the demo).
3. NOVA reads the internal Gmail inbox for messages from the configured supplier, retrieves full text
   and attachments, routes by [NOVA:UUID], validates the approved contact, and queues evaluation.
   NOVA never marks messages read or moves them. Do not add Gmail send/read nodes to n8n.
4. Response example:
   {"results":[{"gmail_id":"abc123","id":"MESSAGE_UUID","status":"queued","duplicate":false}],
    "next_page_token":null}
   duplicate:true is also success. Queued does not mean evaluation completed or data was approved.
5. Paginate: pass next_page_token as the query parameter page_token on the next request. Stop only
   when next_page_token is null. Use built-in HTTP pagination, updating a query parameter per request;
   the first request has no token. Do not process just the first page and silently skip older mail.
6. Results with status:manual_review include a safe reason and Gmail ID. Collect them visibly for the
   operator. They remain in Gmail; there is no separate persistent NOVA queue for these failures yet.
   Missing case references, unsupported attachments, and contact conflicts require manual routing.
7. HTTP 503 means Gmail access/read failed (including missing OAuth consent). HTTP 401/403 means
   the NOVA credential is invalid. Show a failed execution; no indefinite retries. Bounded transient
   retries are safe because NOVA deduplicates ingestion. Do not approve or retry email delivery jobs.

IMPLEMENTATION REQUIREMENTS
- Use current built-in n8n nodes; no unverified community packages.
- NOVA handles binary attachments; n8n carries only references and processing results.
- On failure, report workflow name, step, execution/message reference, and status code. Do not send full
  email bodies, attachments, or credentials to an external notification channel.
- Explain how to limit retained execution data because supplier emails can contain identifying information.
- Add clear node labels and setup notes. Do not invent backend endpoints.
- If you can generate only one workflow at a time, generate Workflow 1 first, then Workflow 2.

Return the workflows plus credential/setup instructions and a short test checklist covering manual
triggering, duplicate replies, a PDF attachment, multiple attachments, missing case reference, sender
mismatch, and a temporary backend failure. Do not activate or publish until I configure and test them.
```
