# NOVA frontend integration

The React control center reads everything (cases, drafts, proposals, replies, attachments, jobs,
audit) from the live backend — no mock fallback; failures show explicitly.

## Run it

```bash
docker compose up -d --build api worker
```

Open http://localhost:8000/ (frontend and API share an origin; `/docs` still has the API schema).
Sign in with `NOVA_REVIEWER_TOKEN` from `.env` — the browser exchanges it for a signed HttpOnly,
SameSite=Strict, 8-hour session cookie; the token itself is never embedded in the JS bundle or
stored in localStorage. For HTTPS hosting set `NOVA_COOKIE_SECURE=true` and keep the UI and `/api`
on the same public origin.

## Frontend development

```bash
npm ci
npm run dev
```

Vite serves `127.0.0.1:5173` and proxies `/api` to `127.0.0.1:8000` (preserving Host, so same-origin
sign-in still works). Override with `NOVA_API_URL` on the Vite process only. For a plain Python API
process, `npm run build` first so it can serve the frontend from port 8000 (`FRONTEND_DIST`).

## Review workflow

1. **Import CSV** → preview → **Approve import into database**. Approve any missing contact per case.
2. Open a case, approve its contact if missing/changed (invalidates old drafts).
3. **Start process** (or **Check due cases**) prepares a draft — never approves or sends it.
4. Review recipient/subject/body, save edits (new version), then **Approve email & send**. Same
   explicit approval applies to reminders/follow-ups when auto-send is off.
5. **Sync inbox** ingests all pages of replies, dedupes, and flags anything needing manual routing.
6. **Supplier review**: each reply shows its full text, attachments, and every proposal (new/changed/
   unchanged), editable in one table. Decide all of them and submit once — this calls
   `POST /messages/{id}/approve-all`, which commits the whole batch or none of it.
7. Case closure and follow-ups wait until every reply is reviewed.
8. **Activity** shows jobs/audit; retry failed evaluations or definitely-rejected sends. An
   uncertain send needs a checked Gmail outcome before continuing.
9. **Export CSV** for accepted values. The overview refreshes every 15s, an open case every 10s
   (paused while there are unsaved edits).

## Browser API

`/api` prefix; unprefixed endpoints still work for existing integrations. `POST /api/session`
(`{"token":"..."}`, same-origin only) signs in; `GET /api/session` returns state + a CSRF value
required as `X-NOVA-CSRF` on writes; `DELETE /api/session` signs out. Automation tokens can't open
a reviewer session. Approvals (`/api/drafts/{id}/approve`, `/api/messages/{id}/approve-all`) require
the exact displayed `version`; conflicts reload the case rather than auto-retrying.

## Validation

```bash
uv run pytest -q
npx playwright install chromium
npm run test:ui
```

Browser tests run against an isolated backend (disposable SQLite, simulated mail/fixture eval) —
never `.env`, real providers, or the running PostgreSQL data. Use `NOVA_TEST_DATABASE_URL`
(PostgreSQL) to also run the backend concurrency tests.
