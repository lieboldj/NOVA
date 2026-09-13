# NOVA supplier portal

NOVA emails suppliers for missing sustainability/compliance data, reads their replies and attachments,
and proposes updates to supplier records.

- A reviewer approves the **first** email per case. Follow-ups and reminders after that send
  automatically after a short delay (default 2 minutes, `AUTO_SEND_DELAY_MINUTES`), giving a reviewer
  time to edit or cancel one before it goes out.
- A reviewer approves **every reply's proposed data changes** in one editable batch screen
  (`POST /messages/{id}/approve-all`) — nothing becomes an accepted record without that approval.
- Gemini only ever reads evidence **after** Anymize strips names/emails/IDs from it. It proposes values
  with a cited source quote; it never drafts or sends email.

## Try it

**Cloud demo:** https://nova-bnw6dmyvva-ey.a.run.app (n8n: https://nova-n8n-bnw6dmyvva-ey.a.run.app).
Login kept privately in `.data/cloud/access.txt`. Real Gmail/Anymize/Gemini calls are verified live —
see **Proof it's live** in [`docs/cloud-deployment.md`](docs/cloud-deployment.md) (real message IDs, a
3.8s Gmail-push round trip, a real extracted value with citation). Reproduce it yourself:

```bash
uv run python scripts/verify_cloud.py          # re-checks the deployed access/workflow behavior
uv run python scripts/check_cloud_workflow.py  # sends one real fictional request + reply
uv run python scripts/check_anymize.py --ocr --with-gemini   # locally, against your own keys
```

Any reviewer can also call `GET /audit` for the system's own record of every draft, approval, send, and
automation tick that actually happened.

**Run locally:**

```bash
uv sync
uv run python scripts/init_local.py
docker compose up -d --build api worker
```

Open http://localhost:8000/ (portal) and http://localhost:8000/docs (API). Sign in with the
`NOVA_REVIEWER_TOKEN` from `.env`. See [frontend setup](docs/frontend-integration.md) for the dev server
and browser tests, and [`config/example.env`](config/example.env) for every setting.

## Reference

| Topic | Doc |
|---|---|
| API request/response shapes, review flow | [docs/backend-api.md](docs/backend-api.md) |
| Frontend dev setup | [docs/frontend-integration.md](docs/frontend-integration.md) |
| Gmail OAuth + n8n contract | [docs/gmail-setup.md](docs/gmail-setup.md) |
| n8n workflow generation prompt | [docs/n8n-workflow-ai-prompt.md](docs/n8n-workflow-ai-prompt.md) |
| Google Cloud deployment, verified behavior, cost | [docs/cloud-deployment.md](docs/cloud-deployment.md) |
| Remaining integration/deployment work | [docs/integration-deployment-plan.md](docs/integration-deployment-plan.md) |
| Three-minute demo script | [docs/demo.md](docs/demo.md) |
| Privacy/anonymization walkthrough | [docs/privacy-demo.md](docs/privacy-demo.md) |
| 20-supplier fictional demo | [examples/colleague-demo](examples/colleague-demo/README.md) |
| 100-supplier fictional demo | [examples/colleague-demo/demo100](examples/colleague-demo/demo100/README.md) |

## Verification

```bash
uv run pytest -q
uv run ruff check nova tests scripts migrations
uv run python scripts/check_gemini.py
```

## Changelog

- Added a 100-supplier fictional dataset (`DEMO100`) for scale testing.
- Follow-up/reminder emails now send automatically after a short delay; the first email per case still
  needs manual approval.
- Reply review is now one editable batch per reply (`approve-all`) instead of one approval per field.
- Verified live Gmail push delivery: a real email reaches an n8n webhook execution in ~3.8s, no manual sync.
- Deployed and verified NOVA + n8n on Google Cloud (`aiwomen26ham-4415`, `europe-west3`).
- Switched to `gemini-3.8-flash`; connected the React control center to live backend approvals.
