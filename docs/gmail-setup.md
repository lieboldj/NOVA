# Gmail test integration

NOVA's internal mailbox is **devstar4415@gcplab.me**; the supplier test mailbox is
**devstar4418@gcplab.me**. **Only the internal account needs OAuth** — log into the supplier
account in Gmail to reply manually; NOVA never authenticates as the supplier. Outgoing NOVA
requests are stamped and excluded from inbox ingestion. `.env` selects `MAIL_MODE=gmail`;
credentials are never in source control or the Docker image. See [cloud-deployment.md](cloud-deployment.md).

The hosted demo has a labelled internal reply simulator enabled (`DEMO_AUTO_REPLY=true`) for the
20 `DEMO20` cases — it does not send from 4418. Set it `false` to test genuine 4418 replies.

## Authorize the internal mailbox

1. Enable the **Gmail API**, configure the consent screen (add `devstar4415@gcplab.me` as a test
   user), request `gmail.readonly` + `gmail.send`.
2. Create a **Desktop app** OAuth client, download its JSON to `.data/gmail-client.json`.
3. Run `uv run python scripts/connect_gmail.py`, choose `devstar4415@gcplab.me`, grant both scopes.
   Saves the refresh token to `.env` (mode 0600). Forward local port 8765 for a remote dev host.
4. `docker compose up -d --build api worker`.
5. `uv run python scripts/nova_cli.py GET /mail/gmail/status` — require `connected: true`.

([Desktop OAuth quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python),
[Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes).)

## Frontend and n8n contract

Reviewer credentials for the frontend, automation credentials for n8n — the model gets neither.

| Action | Endpoint | Role |
| --- | --- | --- |
| Connection status | `GET /mail/gmail/status` | Reviewer |
| List / read inbox messages | `GET /mail/gmail/inbox?page_token=...`, `GET /mail/gmail/messages/{id}` | Reviewer |
| Ingest a page of replies | `POST /automation/gmail/sync?page_token=...` | Automation or reviewer |
| Approve email / retry send | `POST /drafts/{id}/approve`, `POST /jobs/{id}/retry` | Reviewer |
| Approve reply data | `POST /messages/{id}/approve-all` | Reviewer |

Approve the contact (`POST /cases/{id}/contact/approve`) before drafting. Keep `[NOVA:case-uuid]`
in edited subjects for routing. Import `integrations/n8n/sync-gmail.json`, set its Header Auth
credential + backend URL, test manually before scheduling.

Sync follows `next_page_token` until null (≤20 messages/page), leaves Gmail read state/labels
untouched, and dedupes by Gmail ID. Messages with no case reference, a mismatched contact,
unsupported files, or oversized content return `status: manual_review` and stay in the mailbox for
a later scan — there's no separate persistent review queue yet. Supported evidence: full email
text plus PDF/UTF-8 TXT attachments, ≤10 attachments / 10 MiB combined.

Sends use Gmail's `messages.send`. A definite rejection is retried with the same approved version;
a timeout/ambiguous failure becomes `uncertain` and needs manual reconciliation, not a blind retry.

## Test sequence

1. Authorize Gmail, confirm `status` shows the right account.
2. Import demo data, approve a contact, create + approve a draft.
3. Confirm nothing reaches the supplier inbox before approval.
4. Reply with requested values + a PDF; sync (`/automation/gmail/sync` or the n8n workflow); repeat
   to check deduplication.
5. With Anymize configured, review the extracted proposals and approve via `approve-all`.

(Automated Gmail tests mock Google's API — they check approval gates, ingestion, dedup, and
pagination, not live OAuth or real mailbox delivery.)

## Authorizing a second mailbox

A downloaded OAuth client JSON only identifies the app — the account still has to grant access once:

```bash
uv run python -m scripts.connect_gmail \
  --client /path/to/new-client.json \
  --mailbox devstar4418@gcplab.me \
  --output .data/gmail-supplier-credentials.json
```

Never commit either credential file. If the new client is meant for NOVA's *watched* internal
mailbox, its Gmail Pub/Sub topic must belong to the same Google project as that OAuth client.
