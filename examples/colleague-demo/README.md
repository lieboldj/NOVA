# Colleague demonstration: 20 fictional suppliers

Open https://nova-bnw6dmyvva-ey.a.run.app, sign in, search **DEMO20** for these 20 suppliers
(1–20 outstanding fields each, including some unchanged-confirmation cases).

## Five-minute walkthrough

1. Compare suppliers with 1, 5, 12 and 20 outstanding fields.
2. Open **Demo Birch Packaging** (DEMO20-02) → **Email** to see the real request sent to 4418.
3. **Supplier review** — the reply is labelled simulated, but Gemini's extraction is real.
4. Try **Suggested spelling correction** → **Use suggested correction** → **Save proposed value** → approve.
5. Compare DEMO20-04 (PDF evidence) and DEMO20-20 (scanned PDF/OCR).
6. Approve/reject proposals (incl. unchanged confirmations), then complete the reply review.

## How the replies work

Requests are real (sent to 4418); replies are generated internally (`DEMO_AUTO_REPLY=true`) — never
sent from the supplier mailbox — rotating through plain text, TXT, PDF, mixed, and scanned-PDF/OCR
formats, several with intentional typos, all processed live through Anymize + Gemini. To test genuine
replies instead, disable `DEMO_AUTO_REPLY` and reply from 4418 yourself, keeping the subject.

## Suppliers

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

Region/industry filter on imported metadata only — category applicability is never inferred.

## Reuse

```bash
uv run python -m scripts.prepare_colleague_demo --load
```

Preserves existing cases, skips suppliers already loaded, never approves sending. All names/values
are fictional.
