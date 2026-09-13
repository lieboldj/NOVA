# Gmail test integration

Current hosted configuration: **4415 sends to devstar4418@gcplab.me**. DEMO20 requests
have a clearly labelled internal response simulator enabled; it does not send mail from
4418. Set `DEMO_AUTO_REPLY=false` on API and worker to test genuine replies from 4418.
Outgoing NOVA requests are stamped and excluded from inbox ingestion.
The former single-mailbox setup remains available by changing `GMAIL_SUPPLIER` and
approving the corresponding case contacts; internal demo responses require the 4418 test contact.
See [cloud verification and operation](cloud-deployment.md).

NOVA's internal mailbox is **devstar4415@gcplab.me**. The supplier test mailbox is
**devstar4418@gcplab.me**. Only the internal account needs OAuth authorization. Log into the supplier
account in Gmail to reply manually. Backend sending is restricted to this configured supplier address.

The Gmail transport and inbox tools are implemented. Actual connection requires Google OAuth consent;
knowing the addresses does not provide access. Local `.env` selects `MAIL_MODE=gmail`; credentials are
never included in source control or the Docker image.

## Authorize the internal mailbox

1. In your Google Cloud project, enable the **Gmail API**. Configure the Google Auth Platform consent
   screen, add `devstar4415@gcplab.me` as a test user when using an external testing application,
   and request `gmail.readonly` and `gmail.send` permissions.
2. Create an OAuth client with application type **Desktop app**. Download its JSON into
   `.data/gmail-client.json` in this repository. Do not paste credentials into chat.
3. Run `uv run python scripts/connect_gmail.py` on the computer where you can open the browser.
   Choose **devstar4415@gcplab.me** and grant the two permissions. The script checks the account
   before saving the refresh token and OAuth client credentials to ignored `.env` with mode 0600.
   For a remote development host, forward localhost port 8765 to that host before starting the script.
4. Reload the API and worker with `docker compose up -d --build api worker`.
5. Run `uv run python scripts/nova_cli.py GET /mail/gmail/status`. Require `connected: true` before
   testing delivery. Missing credentials or an incorrect account keep sending blocked.

Google documents [Desktop OAuth setup](https://developers.google.com/workspace/gmail/api/quickstart/python)
and the [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes).

## Frontend and n8n contract

All requests use NOVA Bearer authentication. The frontend uses reviewer credentials; n8n uses only the
separate automation credential. The model has neither credential and receives sanitized evidence.

| Action | Endpoint | Role |
| --- | --- | --- |
| Verify internal Gmail connection | `GET /mail/gmail/status` | Reviewer |
| List supplier messages in the internal inbox | `GET /mail/gmail/inbox?page_token=...` | Reviewer |
| Read full message text and attachment metadata | `GET /mail/gmail/messages/{gmail_message_id}` | Reviewer |
| Ingest a page of supplier replies and queue evaluation | `POST /automation/gmail/sync?page_token=...` | Automation or reviewer |
| Review/edit email | `GET /drafts`, `PATCH /drafts/{id}` | Reviewer |
| Approve the exact email version and queue delivery | `POST /drafts/{id}/approve` with `{"version":1}` | Reviewer |
| Inspect delivery/evaluation jobs | `GET /jobs` | Reviewer |
| Retry a definitely rejected Gmail send after fixing access | `POST /jobs/{id}/retry` | Reviewer |
| Approve the exact proposed data version | `POST /proposals/{id}/approve` with `{"version":1}` | Reviewer |

Approve the test case's supplier contact with `POST /cases/{id}/contact/approve`, supplying its current
`revision` and `recipient: devstar4418@gcplab.me`, before creating its draft. Existing case contacts are
not silently overwritten by mail configuration. Preserve `[NOVA:case-uuid]` in edited subjects so replies
can be routed. An email send approval covers that version only; edits and case changes invalidate it.

Import `integrations/n8n/sync-gmail.json` into n8n, configure its HTTP Header Auth credential and backend URL,
and test it manually before enabling the schedule. This import has been checked as JSON; it has not yet
been executed on your partner n8n instance.

The sync response contains `results` and `next_page_token`. Follow the token until null; each page has
at most 20 messages. Gmail list uses `nextPageToken` (Google's spelling), while NOVA sync uses
`next_page_token`. Duplicate Gmail IDs return the existing NOVA message without a second evaluation.
Sync leaves Gmail read/unread state and labels unchanged. It scans supplier messages in the inbox,
including already-read messages; archived mail is outside this test workflow.

Messages with no unique case reference, a mismatched approved contact, unsupported files, or oversized
content return `status: manual_review` with a reason. Inspect these in the n8n execution result and in
Gmail; they remain in the mailbox and are retried on later scans. There is no separate persistent review
queue for un-ingested Gmail messages yet. Route manually through the existing multipart ingestion
endpoint once resolved. Supported evidence is full email text plus PDF and UTF-8 TXT attachments,
up to 10 attachments and 10 MiB combined. Ingested originals are available through protected
`/messages/{id}` and `/documents/{id}` endpoints.

Sending uses Google's [messages.send API](https://developers.google.com/workspace/gmail/api/guides/sending).
A definite rejection is retryable with the existing approved version; the worker rechecks approval on
retry. A timeout, interrupted send, or ambiguous server failure becomes `uncertain` and requires manual
reconciliation against Gmail before another attempt. Every reminder and follow-up has its own approval.

## Test sequence

1. Authorize Gmail and confirm the status endpoint reports the correct connected account.
2. Import the demo data, approve a case contact, and create an email draft.
3. Confirm that the supplier inbox receives nothing before frontend approval. Approve the current draft.
4. Check the delivery job and supplier Gmail inbox. Reply with requested values and a PDF attachment.
5. Trigger `/automation/gmail/sync` manually or use the n8n workflow. Repeat to verify deduplication.
6. With Anymize configured, the worker extracts proposals. Review evidence and approve selected changes.
   Accepted supplier values remain unchanged before this data approval. Anymize credentials are still
   independently required for Gemini extraction; do not use fixture anonymization with live mail.

The automated Gmail tests mock Google's HTTP API: they verify approval gates, exact email content,
account and recipient restrictions, ingestion, attachment fetching, pagination, deduplication, and
ambiguous send handling. They do not establish live OAuth access or prove delivery into a real mailbox.
