# DEMO100 — fictional supplier scale fixture

All names, IDs, products, declarations and historical dates are synthetic. Any resemblance to a real company is coincidental. This set is separate from the existing DEMO20 fixtures.

- `suppliers.csv`: import file with the exact V2_COLUMNS order plus the supported Region and Industry columns; 100 suppliers, 300 article cases (three NARTs each), 6,600 field rows.
- `article-index.csv`: a convenient list of suppliers, articles, countries, industries and outstanding counts. This index is **not** an import file.
- Five industries: automotive, packaging, electronics, textiles and industrial equipment. Twenty countries across EMEA, AMER, LATAM and APAC.
- Each article has 22 fields, with 1–20 outstanding (3,150 total), at least one Complete field and an informational N/A field. Outstanding entries mix Missing, Outdated and Flagged (needs supplier confirmation).
- MDF covers industry questions and quality evidence; PCF covers footprint, energy and logistics. Three DEMO100 module IDs intentionally avoid claiming these fictional questionnaires are an official compliance catalogue. Categories are seeded for the industry; the agent does not infer legal applicability.

Regenerate deterministically from the repository root:

```sh
uv run python -m scripts.prepare_demo100
```

For offline testing, use a separate database with `AI_MODE=fixture`, `ANONYMIZER_MODE=fixture`, `MAIL_MODE=simulation` and `DEMO_AUTO_REPLY=false`. Import `suppliers.csv`, preview it, then approve the import. Approve a test contact on selected cases and prepare their initial drafts. Initial requests remain manually approved; no send jobs are created simply by importing this dataset.

After simulated sending, submit replies through `/cases/{id}/messages` with the approved sender and exact field references, for example `DEMO100-001-A01-F01=Drawing DEMO100 revision 4`. The fixture extractor accepts `field-id=value` lines in email text or TXT/PDF evidence. Include only some requested fields to test incomplete replies; use an invalid date to test correction or rejection in the bulk review table.

Enable `AUTO_FOLLOWUP_ENABLED=true` for incomplete-answer automation. `AUTO_SEND_FOLLOWUPS=true` enables delayed follow-ups/reminders; `AUTO_SEND_DELAY_MINUTES=2` supplies the reviewer window. To exercise reminder cadence offline without waiting days, set a **test database** case's `next_action_at` into the past after initial simulated delivery, call `/automation/tick`, and advance the queued job's `available_at` in that test database. Repeat to verify `MAX_REMINDERS` escalation. Historical CSV contact dates are field metadata: importing them does not fabricate sent emails or overdue case timers.

`uv run pytest tests/test_demo100.py` exercises import, selected initial approval, delayed reminder, evidence extraction and bulk approval without remote services. The generator and tests never contact Gmail, Anymize or Gemini. No contacts, credentials or live-send approvals are bundled. For a later live exercise, configure the providers and approved test mailbox separately and approve only the selected initial emails. The existing DEMO20 reply simulator does not automatically run for DEMO100.
