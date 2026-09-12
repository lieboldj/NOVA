# NOVA frontend integration

The React control center is connected to the FastAPI backend. Case counts, suppliers, statuses, email
drafts, proposed values, replies, attachments, jobs, and audit events come from the database. There is no
fallback to the original mock dashboard. Unavailable services and request failures are displayed explicitly.

## Run the complete portal

```bash
docker compose up -d --build api worker
```

Open **http://localhost:8000/**. The Docker build compiles the React app and packages its static assets in
the API image. The frontend and API share an origin. Existing API documentation remains at `/docs`;
existing n8n and CLI endpoints remain valid.

Sign in with the local `NOVA_REVIEWER_TOKEN` value from `.env`. This is the existing reviewer access key,
not the Gmail, Anymize, Gemini, or automation key. Retrieve it locally through your editor; do not paste
it into chat, build variables, URLs, or source files. The browser exchanges it for a signed HttpOnly,
SameSite=Strict, eight-hour session cookie. The UI clears its access-key input after login. Neither the
API token nor provider credentials are embedded in the JavaScript bundle or saved in localStorage.

This demo still uses one configured reviewer identity. Individual enterprise sign-in remains a deployment
task. For HTTPS hosting, set `NOVA_COOKIE_SECURE=true` and preserve the original Host and scheme through
the reverse proxy. Use the same public origin for the UI and `/api`; unrestricted CORS is unnecessary.

## Frontend development

Use Node 24 and npm with the checked-in lockfile:

```bash
npm ci
npm run dev
```

Vite serves `http://127.0.0.1:5173` and proxies `/api` to `http://127.0.0.1:8000`. The proxy preserves Host
so the backend can verify same-origin sign-in. To use a different backend, set `NOVA_API_URL` only on
the Vite server process. No credentials are injected by this proxy.

For a local Python API process, run `npm run build` before starting it to serve the frontend from port
8000. `FRONTEND_DIST` defaults to `dist`. `npm run preview` has the same API proxy for build checks.

## Start a process from the portal

Use **Start process** on the overview to open the guided conversation. Search for a supplier or article,
select its case, and review the outstanding fields. If its contact is missing or changed, approve the
recipient first. **Prepare request for review** creates a pending draft and opens the email review screen;
it does not approve or send the email. Existing drafts and replies needing review are opened instead of
starting duplicate requests. When no cases exist, the starter guides you through CSV import and returns
to supplier selection after import approval.

The starter uses backend records and explicit choices. It does not send chat text or supplier identities
to a model. **Check due cases** runs the separate scheduled-work check across existing due cases.

## Review workflow

1. Import CSV: upload and preview its sample, counts, and optional contacts. Only **Approve import into
   database** adds accepted supplier records. Unknown contact addresses can be approved later per case.
2. Open a case. Approve its supplier contact if missing or incorrect. Contact changes invalidate old drafts.
3. Create a draft or use **Check due cases** to check due cases. This prepares drafts; it does not approve them.
4. Review recipient, subject, and body. Save edits as a new version, then press **Approve email & send**.
   Delivery is queued to the worker; the status updates when Gmail accepts it. Reminders and follow-ups
   use this same explicit approval. The test Gmail transport only sends to its configured supplier mailbox.
5. **Sync inbox** ingests every page of supplier replies. It handles duplicate IDs and reports messages
   requiring manual routing in Alerts. Those routing results are displayed for the current browser session;
   the originals remain in Gmail. n8n can call the same endpoint on its schedule.
6. In **Data changes**, inspect the accepted value, proposed value, rationale, and source quote. Edit/save
   if needed, then approve or reject each field separately. Email approval cannot approve supplier data.
7. **Replies** exposes full email text and protected attachment downloads. Complete reply review after
   deciding all proposals to allow a follow-up for any remaining missing fields.
8. **Activity** shows case jobs and audit history. Failed evaluations and definitely rejected sends can
   be retried. Uncertain email deliveries require checking Gmail and recording the confirmed outcome.
9. Export CSV to download accepted values. Search, status/supplier filters, statistics, and alerts use live
   case records. The overview refreshes every 15 seconds; an open case refreshes every 10 seconds while
   there are no unsaved email/proposal edits.

The UI reads provider configuration flags at runtime. Missing Anymize access is shown as blocked reply
evaluation; it does not invent proposals or bypass sanitization. Configured flags do not guarantee provider
health. Safe worker errors remain available in Activity.

## Browser API and approval contract

Browser requests use the `/api` prefix. Original unprefixed endpoints remain supported for existing
integrations. `POST /api/session` accepts `{"token":"<reviewer access key>"}` only from the same origin.
`GET /api/session` returns authentication state and a CSRF value; mutating requests must include that
value as `X-NOVA-CSRF`. `DELETE /api/session` signs out. Automation bearer tokens cannot create reviewer
sessions or approve changes. API responses are not cached.

New case read endpoints are `/api/cases/{id}/messages`, `/api/cases/{id}/activity`, and
`/api/jobs?case_id={id}`. Email approval uses `/api/drafts/{id}/approve`; field approval uses
`/api/proposals/{id}/approve`. Both require the exact displayed `version`. Conflicts reload the current
case for review; the frontend never retries an approval automatically with a newer version.

## Validation

```bash
uv run pytest -q
npx playwright install chromium
npm run test:ui
```

Browser tests compile the production bundle and start an isolated backend on port 8011 with a disposable
SQLite database and simulated mail/fixture evaluation. They exercise import, editing, email approval,
reload persistence, reply ingestion, proposal review, data approval, sign-out, and mobile layout. They
never load `.env`, call real providers, or alter the running PostgreSQL data. Use a dedicated `nova_test`
PostgreSQL database through `NOVA_TEST_DATABASE_URL` to run backend concurrency tests.
