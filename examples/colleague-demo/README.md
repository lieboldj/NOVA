# Colleague demonstration: 20 fictional suppliers

Open https://nova-bnw6dmyvva-ey.a.run.app and sign in using the reviewer access key.
Search **DEMO20** to show exactly these 20 suppliers. Each has two outstanding fields
and one existing value to demonstrate unchanged confirmations.

## Five-minute walkthrough

1. Show the supplier list, then open **Demo Alder Motion** (DEMO20-01).
2. Review the missing certificate expiry and supporting evidence reference.
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

| ID | Supplier | Region / industry | Reason to contact |
|---|---|---|---|
| DEMO20-01 | Demo Alder Motion | EMEA / Automotive | Missing quality certificate expiry |
| DEMO20-02 | Demo Birch Packaging | EMEA / Packaging | Outdated recycled content |
| DEMO20-03 | Demo Cedar Circuits | APAC / Electronics | Conflicting material composition |
| DEMO20-04 | Demo Dune Fabrics | APAC / Textiles | Missing country of manufacture |
| DEMO20-05 | Demo Ember Components | AMER / Industrial | Outdated energy sourcing statement |
| DEMO20-06 | Demo Fern Motors | APAC / Automotive | Missing product weight |
| DEMO20-07 | Demo Grove Packs | AMER / Packaging | Packaging weight needs confirmation |
| DEMO20-08 | Demo Harbor Sensors | EMEA / Electronics | Expired calibration evidence |
| DEMO20-09 | Demo Iris Weaving | LATAM / Textiles | Missing fibre composition |
| DEMO20-10 | Demo Juniper Tools | EMEA / Industrial | Reporting period needs confirmation |
| DEMO20-11 | Demo Kestrel Mobility | AMER / Automotive | Missing manufacturing site |
| DEMO20-12 | Demo Linden Cartons | LATAM / Packaging | Outdated packaging composition |
| DEMO20-13 | Demo Maple Devices | AMER / Electronics | Product lifetime needs clarification |
| DEMO20-14 | Demo Nacre Textiles | EMEA / Textiles | Missing water consumption data |
| DEMO20-15 | Demo Orchard Machines | LATAM / Industrial | Outdated transport information |
| DEMO20-16 | Demo Pine Drive | LATAM / Automotive | Recycled metal claim needs confirmation |
| DEMO20-17 | Demo Quartz Wrapping | APAC / Packaging | Missing end-of-life guidance |
| DEMO20-18 | Demo Reed Controls | LATAM / Electronics | Outdated certificate expiry |
| DEMO20-19 | Demo Spruce Fibres | AMER / Textiles | Origin claim needs clarification |
| DEMO20-20 | Demo Willow Systems | APAC / Industrial | Missing maintenance instructions |

## Reuse

Run `uv run python -m scripts.prepare_colleague_demo --load` from the configured project workspace.
The loader preserves existing cases, records its import ID before approval, and never approves email sending.
It skips already existing demo suppliers; it does not reset completed cases.
The CSV, manifest and 20 reply files are versioned together. All names and values are fictional.
