# Three-minute interactive demo

Start from the repository root:

```bash
npm ci
npm run demo
```

Open **http://localhost:8012/** and sign in with reviewer access key **`nova-demo`**.
This key is public and only grants access to the local, disposable demo.

The demo preloads one fictional supplier, two missing fields, and a pending email draft. It uses a
separate temporary SQLite database, separate documents, and its own browser session cookie. It does
not load `.env`, call live providers, send real mail, or modify the main portal database.

## Presentation sequence

1. **0:00–0:40 — Email approval.** Open **Demo Circular Materials**. Review the recipient, subject, and
   requested fields. Click **Approve email & send**. The status becomes **Simulated**.
2. **0:40–1:20 — PDF evidence and data approval.** Within about 10 seconds, a scripted supplier reply
   appears. Open **Data changes**: the PDF supplies “80% recycled aluminium.” Show the empty accepted
   value, source quote, and attachment. Click **Approve data change**.
3. **1:20–2:10 — Incomplete reply and follow-up.** Return to **Email**. A follow-up is prepared for the
   missing certificate date (allow up to 10 seconds for refresh). Review and approve that email too.
4. **2:10–3:00 — Complete the case.** A second PDF reply proposes `2027-12-31`. Approve this change in
   **Data changes**. The case closes. Show **Activity** for the recorded approvals, then export the CSV
   from the overview to show accepted values.

Each reply is generated only after the preceding email has been approved and its simulated delivery
has completed. The demo never approves an email or data proposal on the reviewer's behalf. Edits must
be saved and reviewed as a new version before approval.

This is a repeatable workflow demonstration with scripted extraction. It does **not** demonstrate live
Gemini reasoning, Anymize detection quality, Gmail delivery, or n8n scheduling. Those integrations use
the main portal and its separate configuration. The demo UI labels simulation and scripted evaluation.

Stop with Ctrl+C and rerun `npm run demo` for a fresh case. All demo data is discarded on exit. For an
alternative local port after building: `uv run python scripts/run_demo.py --port 8013`.

The normal portal remains at **http://localhost:8000/** with its existing reviewer key and data.
