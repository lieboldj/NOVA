# Colleague demonstration: 20 fictional suppliers

Open https://nova-bnw6dmyvva-ey.a.run.app and sign in using the reviewer access key.
Search **DEMO20** to show exactly these 20 suppliers. Outstanding workloads range from 1 to 20 fields
with existing values to demonstrate unchanged confirmations.

## Five-minute walkthrough

1. Show the supplier list, then open **Demo Alder Motion** (DEMO20-01).
2. Review the one missing certificate expiry; compare with Demo Ember Components, which has 20 outstanding fields.
3. Open the **Email** tab. The request is prepared for the configured test mailbox.
   Click **Approve email & send** when ready. This sends one real demo email.
4. In that mailbox, reply to the request, preserving the entire subject.
   Paste [the prepared reply](replies/DEMO20-01.txt). Sending and receiving use the same test mailbox.
5. Gmail push triggers n8n and NOVA. Refresh NOVA after extraction completes.
6. Open **Supplier review**: show the original reply and all three proposals.
   Expected expiry: **2028-12-31**; the product family is an unchanged confirmation.
7. Approve the values, then mark the entire reply reviewed to complete the case.

All 20 request drafts await human approval. Preparing this dataset does not send emails.
Use each supplier's reply file for the corresponding email; the subject routes it to the right case.
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
