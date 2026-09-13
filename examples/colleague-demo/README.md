# Colleague demonstration: 20 fictional suppliers

Open https://nova-bnw6dmyvva-ey.a.run.app and sign in using the reviewer access key.
Search **DEMO20** to show exactly these 20 suppliers. Outstanding workloads range from 1 to 20 fields
with existing values to demonstrate unchanged confirmations.

## Five-minute walkthrough

1. Show the DEMO20 list and compare suppliers with 1, 5, 12 and 20 outstanding fields.
2. Open **Demo Birch Packaging** (DEMO20-02), then **Email** to show the real request sent to devstar4418@gcplab.me.
3. Open **Supplier review**. The reply is clearly labelled as simulated; Gemini extraction is real.
4. Show the original spelling and the separate **Suggested spelling correction**. To use it, click
   **Use suggested correction**, then **Save proposed value**, then approve after review.
5. Compare Demo Dune Fabrics (DEMO20-04) for PDF evidence and Demo Willow Systems (DEMO20-20) for scanned PDF/OCR.
6. Show all received input, including unchanged confirmations, and approve/reject proposals before completing reply review.

## Automatic and manual replies

The hosted run sends real requests to 4418 and generates fictional replies internally with DEMO_AUTO_REPLY enabled.
The simulator does not send an email from the supplier mailbox. Responses rotate through plain text, prose, TXT, PDF,
mixed email/PDF and scanned PDF; most include intentional spelling mistakes. Anymize and Gemini process them live.
To test genuine supplier email replies instead, disable DEMO_AUTO_REPLY on API and worker, then reply from 4418
to a newly approved request, preserving its subject. Each supplier's reply text file supplies its correct values.
Existing requests in this hosted demo were sent on the user's instruction; no supplier data approvals were automated.
Original supplier records and replies remain in Cloud SQL; Anymize runs before Gemini extraction.

## Supplier list

| ID | Supplier | Region / industry | Outstanding | Reason to contact |
|---|---|---|---|---|
| DEMO20-01 | Demo Alder Motion | EMEA / Automotive | 1 | Missing quality certificate expiry |
| DEMO20-02 | Demo Birch Packaging | EMEA / Packaging | 5 | Outdated recycled content |
| DEMO20-03 | Demo Cedar Circuits | APAC / Electronics | 12 | Conflicting material composition |
| DEMO20-04 | Demo Dune Fabrics | APAC / Textiles | 3 | Missing country of manufacture |
| DEMO20-05 | Demo Ember Components | AMER / Industrial | 20 | Outdated energy sourcing statement |
| DEMO20-06 | Demo Fern Motors | APAC / Automotive | 8 | Missing product weight |
| DEMO20-07 | Demo Grove Packs | AMER / Packaging | 2 | Packaging weight needs confirmation |
| DEMO20-08 | Demo Harbor Sensors | EMEA / Electronics | 15 | Expired calibration evidence |
| DEMO20-09 | Demo Iris Weaving | LATAM / Textiles | 4 | Missing fibre composition |
| DEMO20-10 | Demo Juniper Tools | EMEA / Industrial | 10 | Reporting period needs confirmation |
| DEMO20-11 | Demo Kestrel Mobility | AMER / Automotive | 6 | Missing manufacturing site |
| DEMO20-12 | Demo Linden Cartons | LATAM / Packaging | 18 | Outdated packaging composition |
| DEMO20-13 | Demo Maple Devices | AMER / Electronics | 7 | Product lifetime needs clarification |
| DEMO20-14 | Demo Nacre Textiles | EMEA / Textiles | 14 | Missing water consumption data |
| DEMO20-15 | Demo Orchard Machines | LATAM / Industrial | 9 | Outdated transport information |
| DEMO20-16 | Demo Pine Drive | LATAM / Automotive | 16 | Recycled metal claim needs confirmation |
| DEMO20-17 | Demo Quartz Wrapping | APAC / Packaging | 11 | Missing end-of-life guidance |
| DEMO20-18 | Demo Reed Controls | LATAM / Electronics | 19 | Outdated certificate expiry |
| DEMO20-19 | Demo Spruce Fibres | AMER / Textiles | 13 | Origin claim needs clarification |
| DEMO20-20 | Demo Willow Systems | APAC / Industrial | 17 | Missing maintenance instructions |

## Industry and categories

Industry and region filter suppliers using imported metadata. Category applicability is not inferred by the agent.
This demo explicitly seeds industry-specific questions plus shared product, evidence, energy and logistics categories.
For example, electronics includes standby power and circuit boards; textiles includes fabric and dyeing questions.

## Reuse

Run `uv run python -m scripts.prepare_colleague_demo --load` from the configured project workspace.
The loader preserves existing cases, records its import ID before approval, and never approves email sending.
It skips already existing demo suppliers; it does not reset completed cases.
The CSV, manifest and 20 reply files are versioned together. All names and values are fictional.
