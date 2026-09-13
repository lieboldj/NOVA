# Live integration and privacy check — 12 September 2026

> Policy clarification after this test: Anymize is explicitly approved to process original sensitive
> data, so the required boundary is Anymize → Gemini, not company → Anymize. The findings below are
> a historical record of a real gap at the time, not a current architecture problem.

Anymize, Gemini, and outgoing Gmail all worked live. Fictional evidence and a separate database were
used; no real supplier records were involved.

| Check | Result |
| --- | --- |
| Anymize text + PDF anonymization/restoration | Passed against the live service |
| Gemini extraction after Anymize | Passed — extracted `2028-12-31` with matching evidence |
| Real send | One email `devstar4415@gcplab.me` → `devstar4418@gcplab.me`, confirmed `SENT` (`1a09716082af5bae`) |
| Real supplier reply | Not verified (no supplier mailbox credentials at the time) |
| Synthetic reply ingestion + evaluation | Passed; duplicate reply correctly returned the existing message |
| Gemini request identity check | No seeded supplier/contact/name/email/filename present |
| Data approval boundary | Correct proposal stayed pending; accepted value stayed blank |
| Automated suite | 32 passed, 1 PostgreSQL concurrency test skipped |

Gmail's `SENT` record proves provider acceptance, not inbox delivery — this did not verify a complete
real round trip.

## Privacy gaps found (code inspection)

1. Local identifier replacement ([`nova/providers.py`](../nova/providers.py)) only covers identities
   already on the case — other people, orgs, addresses, and free text still reach hosted Anymize (the
   test directly showed this for a name and an email address).
2. Scanned PDF pages ([`nova/worker.py`](../nova/worker.py)) go to Anymize's `/ocr` endpoint as
   original images before any local replacement — a printed name can leave even for a known supplier.
3. The worker checks Anymize's response *structure*, not whether it actually caught every identity —
   the test's own seeded-identity guard is test instrumentation, not a production safeguard.
4. Gemini intentionally receives sanitized business facts. If the requirement is "no data at all
   leaves the company," remote extraction can't satisfy that — extraction would need to run internally.

**Conclusion at the time:** the requirement "identifying data never leaves the company" was **not**
met — only "identifying data never reaches Gemini unsanitized" was. Fixing the former would need
OCR/anonymization to happen inside the company boundary with a blocking check on anything not cleared.

## Repeating this check

```bash
uv run python scripts/check_live_workflow.py --output .data/live-check-20260912 --send-email
```
(A fresh output directory is needed to send another real test email — reusing one does not resend.)

To test a real reply: reply to the sent test request from `devstar4418@gcplab.me` keeping its subject,
then:
```bash
uv run python scripts/check_live_workflow.py --output .data/live-check-20260912 --sync-replies
```
This queues any matched reply but deliberately skips evaluation while the anonymization gap above is
open. Local evidence files land in the (git-ignored, private-permission) output directory.
