# Live integration and privacy check — 12 September 2026

> Policy clarification after this test: the user explicitly approved Anymize as a processor of
> original sensitive supplier data. The required boundary is therefore Anymize → Gemini, not
> company → Anymize. The observations below remain a historical record; sending originals to
> Anymize is permitted under the clarified policy. The checked Gemini payload passed the seeded
> identity checks. This does not establish complete detection for arbitrary future documents.

Anymize, Gemini, and outgoing Gmail worked in live tests. **The requirement that identifying data
never leave the company through an API is not met by the current architecture.** The test used fictional
supplier evidence and a separate database; no actual supplier records were submitted for testing.

| Check | Result |
| --- | --- |
| Anymize text anonymization, JSON preservation, restoration | Passed against the configured live service |
| Anymize PDF endpoint and restoration | Passed with a generated fictional PDF |
| Gemini structured extraction after Anymize | Passed; extracted `2028-12-31` with matching evidence |
| Actual supplier test request | One email sent from `devstar4415@gcplab.me` to `devstar4418@gcplab.me` |
| Gmail transmission verification | Provider message `1a09716082af5bae` read back with the `SENT` label |
| Supplier inbox receipt / real supplier reply | Not verified: supplier mailbox credentials unavailable; internal inbox sync returned no supplier messages |
| Reply ingestion and PDF evaluation | Passed using an explicitly synthetic reply submitted through NOVA's authenticated API |
| Duplicate reply | Returned the existing message without another evaluation |
| Gemini request identity checks | No seeded supplier name, supplier/article/row ID, contact name, email address, or original filename present |
| Data approval boundary | Correct date proposal remained pending; accepted value remained blank |
| Replaying the test | No second email attempted, verified with the send method blocked |
| Automated suite | 32 passed, 1 PostgreSQL concurrency test skipped at the time of execution |

The request subject is:

```text
[NOVA:c755839c-665b-4f10-b2e5-47785859bfd1] Information request — TEST ONLY / fictional data
```

Gmail's Sent record verifies provider acceptance, not delivery into the recipient's inbox. The response
test verifies ingestion, local identifier replacement, live Anymize processing, live Gemini extraction,
evidence validation, and creation of a pending proposal. It does not verify sending from the supplier
account or a complete real Gmail round trip.

## Observed privacy boundary

The captured request to `https://app.anymize.ai/api/anonymize` contained the fictional personal name
`Max Mustermann` and address `max.mustermann@example.com`. The known supplier name, supplier ID,
article ID, row ID, and approved supplier mailbox had already been replaced locally. Anymize then
removed the personal name and address before the request went to Gemini.

The captured Gemini request contained placeholders, field definitions, a local document UUID, and
the certificate expiry facts. It contained none of the identifiers checked in this test. This is evidence
for this sample only, not proof that arbitrary future supplier messages are anonymous.

Code inspection establishes these remaining gaps:

1. [Local replacement](../nova/providers.py) covers only identities already recorded on the case.
   Other people, organizations, addresses, signatures, and confidential free text can reach the hosted
   Anymize service. The test directly demonstrated this for a person and an email address.
2. [Scanned PDF processing](../nova/worker.py) sends the original PDF page to Anymize's `/ocr`
   endpoint before local text replacement. A supplier name printed in an image can therefore leave
   the company even when that supplier is already known.
3. The worker validates Anymize's response structure but has no independent content check that blocks
   an unrecognized identity missed by Anymize. The extra seeded-identity guard in the live test script
   is test instrumentation, not a production privacy fix.
4. Gemini intentionally receives sanitized business facts and field context. If **no data at all** may
   leave the company, remote extraction cannot satisfy that requirement.

To keep identifying data inside the company, OCR and anonymization must happen inside the company
boundary, with locally held identity mappings and a check that blocks outbound content that has not
been cleared. Send only explicitly permitted sanitized facts to Gemini. If the requirement prohibits
all business data leaving, extraction must also run internally. This check did not change production
provider behavior or certify the external provider's hosting, retention, or contractual arrangements.

## Evidence and repeatability

The following local files are ignored by Git and were created with private file permissions:

- `.data/live-check-20260912/result.json`: delivery, jobs, proposal, and request-boundary observations.
- `.data/live-check-20260912/approved-test-email.json`: exact test request approved under the user's instruction.
- `.data/live-check-20260912/anymize-request-fictional.json`: actual fictional request body before Anymize.
- `.data/live-check-20260912/gemini-request-fictional.json`: actual sanitized Gemini request body; no API key.
- `.data/live-check-20260912/supplier-reply-template.txt`: prepared text for a reply from the supplier account.
- `.data/live-check-20260912/workflow.db`: isolated workflow state, including the pending proposal.

The reusable [live check script](../scripts/check_live_workflow.py) needs the development dependencies.
The command used for the one actual send was:

```bash
uv run python scripts/check_live_workflow.py --output .data/live-check-20260912 --send-email
```

Reusing this directory does not resend the request. A new directory with `--send-email` initiates another
real test request and should only be used when another delivery is intended.

To complete the real reply test, sign into `devstar4418@gcplab.me`, reply to the test request with the
prepared fictional response, and preserve its subject. Then run:

```bash
uv run python scripts/check_live_workflow.py --output .data/live-check-20260912 --sync-replies
```

This invokes NOVA's Gmail sync and queues any matched real replies in the isolated database. This mode
deliberately does not run their evaluation while the known external anonymization gap remains.
At the time of checking, no NOVA API was listening on ports 8000 or 8012 and Compose had only PostgreSQL
running. The live test executed the actual application routes and worker in its test process; continuous
inbox polling and unattended reply processing were not running or verified.
