# DEMO100 — fictional supplier scale fixture

All names, IDs and dates are synthetic. Separate from DEMO20.

- `suppliers.csv` — V2_COLUMNS + Region/Industry; 100 suppliers, 300 article cases (3 NARTs each),
  6,600 fields.
- `article-index.csv` — a convenience index (not an import file).
- 5 industries, 20 countries across EMEA/AMER/LATAM/APAC. 22 fields/article, 1–20 outstanding
  (3,150 total), mixing Missing/Outdated/Flagged, plus one Complete and one N/A field each.
- MDF (industry + quality evidence) and PCF (footprint/energy/logistics) — fictional, not an
  official compliance catalogue; categories are seeded per industry, never legally inferred.

Regenerate: `uv run python -m scripts.prepare_demo100`

## Offline testing

With `AI_MODE=fixture`, `ANONYMIZER_MODE=fixture`, `MAIL_MODE=simulation`, `DEMO_AUTO_REPLY=false`:
import → approve → approve test contacts → prepare drafts (initial requests still need manual
approval). Reply via `/cases/{id}/messages` with `field-id=value` lines, e.g.
`DEMO100-001-A01-F01=Drawing DEMO100 revision 4` — omit fields or use an invalid date to test
incomplete/invalid handling in the bulk review table.

`AUTO_FOLLOWUP_ENABLED=true` + `AUTO_SEND_FOLLOWUPS=true` (`AUTO_SEND_DELAY_MINUTES` for the
reviewer window) exercise the automatic follow-up/reminder path. `uv run pytest
tests/test_demo100.py` covers import, approval, reminders, extraction, and bulk approval — no
Gmail/Anymize/Gemini calls, no bundled credentials.

## Live/hosted use

DEMO100 supports the same reply simulator as DEMO20: with `DEMO_AUTO_REPLY=true`, an approved,
sent request queues a labelled fictional reply (text/TXT/PDF/mixed/scanned formats, some
incomplete/invalid) through real Anymize/Gemini — still subject to normal review. Keep
`AUTO_SEND_FOLLOWUPS=false` on the hosted demo so every outgoing email stays manually approved.
`answers.json` holds the synthetic answers (regenerated with the CSV).

```sh
uv run python -m scripts.prepare_demo100_cloud
```

Assigns the existing demo mailbox to blank contacts and prepares drafts — never approves, sends,
or overwrites a different contact. Then in NOVA: open a case, review, **Approve email & send**.
