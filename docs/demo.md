# Three-minute interactive demo

```bash
npm ci
npm run demo
```

Open http://localhost:8012/, sign in with the public demo key **`nova-demo`**. Runs on a separate
disposable SQLite database/session — no `.env`, live providers, real mail, or main-database writes.

## Sequence

1. **0:00–0:40** — **Start process** → **Demo Circular Materials** → inspect missing fields →
   **Prepare request for review** → review → **Approve email & send** (status: Simulated).
2. **0:40–1:20** — a scripted reply with a PDF appears in **Supplier review** ("80% recycled
   aluminium"). Approve the change, then **Complete reply review**.
3. **1:20–2:10** — a follow-up drafts for the missing certificate date; review and approve it too.
4. **2:10–3:00** — a second reply proposes `2027-12-31`; approve it, **Complete reply review**
   (case closes). Show **Activity**, then export the CSV.

Each reply only appears after the prior email is approved and its simulated send completes —
nothing is ever approved automatically here. This demonstrates the workflow with **scripted**
extraction, not live Gemini/Anymize detection, Gmail delivery, or n8n scheduling (those run in the
main portal instead).

Ctrl+C and rerun for a fresh case (all demo data is discarded). Alternate port:
`uv run python scripts/run_demo.py --port 8013`. The real portal stays at http://localhost:8000/.
