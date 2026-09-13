"""Generate a fictional 20-supplier demo; --load imports and prepares unsent cloud drafts."""

import argparse
import csv
import json
from pathlib import Path

import httpx

from nova.workflow import CSV_COLUMNS, parse_csv
from scripts.deploy_cloud import ROOT, save, values

DEST = Path("examples/colleague-demo")
# Name, reason, region, industry, primary label, type, prior value, status, answer.
SUPPLIERS = [
    (
        "Alder Motion",
        "Missing quality certificate expiry",
        "EMEA",
        "Automotive",
        "Quality certificate valid until",
        "Date",
        "",
        "Missing",
        "2028-12-31",
    ),
    (
        "Birch Packaging",
        "Outdated recycled content",
        "EMEA",
        "Packaging",
        "Recycled content statement",
        "Freetext",
        "30% recycled paper",
        "Outdated",
        "75% recycled paper",
    ),
    (
        "Cedar Circuits",
        "Conflicting material composition",
        "APAC",
        "Electronics",
        "Material composition",
        "Freetext",
        "Copper content reported as both 40% and 60%",
        "Flagged (needs supplier confirmation)",
        "60% copper and 40% polymer",
    ),
    (
        "Dune Fabrics",
        "Missing country of manufacture",
        "APAC",
        "Textiles",
        "Country of manufacture",
        "Freetext",
        "",
        "Missing",
        "Portugal",
    ),
    (
        "Ember Components",
        "Outdated energy sourcing statement",
        "AMER",
        "Industrial",
        "Electricity sourcing statement",
        "Freetext",
        "2024 grid electricity",
        "Outdated",
        "2026 electricity supplied from renewable sources",
    ),
    (
        "Fern Motors",
        "Missing product weight",
        "APAC",
        "Automotive",
        "Net product weight",
        "Freetext",
        "",
        "Missing",
        "1.25 kg per unit",
    ),
    (
        "Grove Packs",
        "Packaging weight needs confirmation",
        "AMER",
        "Packaging",
        "Packaging weight per unit",
        "Freetext",
        "Reported as 120 g and 150 g",
        "Flagged (needs supplier confirmation)",
        "120 g per unit",
    ),
    (
        "Harbor Sensors",
        "Expired calibration evidence",
        "EMEA",
        "Electronics",
        "Calibration certificate valid until",
        "Date",
        "2025-12-31",
        "Outdated",
        "2028-06-30",
    ),
    (
        "Iris Weaving",
        "Missing fibre composition",
        "LATAM",
        "Textiles",
        "Fibre composition",
        "Freetext",
        "",
        "Missing",
        "80% cotton and 20% polyester",
    ),
    (
        "Juniper Tools",
        "Reporting period needs confirmation",
        "EMEA",
        "Industrial",
        "Reporting year",
        "Freetext",
        "2024 or 2025",
        "Flagged (needs supplier confirmation)",
        "2026",
    ),
    (
        "Kestrel Mobility",
        "Missing manufacturing site",
        "AMER",
        "Automotive",
        "Manufacturing site reference",
        "Freetext",
        "",
        "Missing",
        "Fictional Demonstration Plant A",
    ),
    (
        "Linden Cartons",
        "Outdated packaging composition",
        "LATAM",
        "Packaging",
        "Packaging material composition",
        "Freetext",
        "Mixed plastic packaging",
        "Outdated",
        "95% paperboard and 5% paper adhesive",
    ),
    (
        "Maple Devices",
        "Product lifetime needs clarification",
        "AMER",
        "Electronics",
        "Expected product lifetime",
        "Freetext",
        "5 years or 50000 hours",
        "Flagged (needs supplier confirmation)",
        "5 years under normal operating conditions",
    ),
    (
        "Nacre Textiles",
        "Missing water consumption data",
        "EMEA",
        "Textiles",
        "Water consumption per product",
        "Freetext",
        "",
        "Missing",
        "12 litres per product",
    ),
    (
        "Orchard Machines",
        "Outdated transport information",
        "LATAM",
        "Industrial",
        "Primary transport mode",
        "Freetext",
        "Air freight",
        "Outdated",
        "Rail freight for the main delivery route",
    ),
    (
        "Pine Drive",
        "Recycled metal claim needs confirmation",
        "LATAM",
        "Automotive",
        "Recycled aluminium content",
        "Freetext",
        "Unverified 80% recycled aluminium",
        "Flagged (needs supplier confirmation)",
        "80% recycled aluminium by mass",
    ),
    (
        "Quartz Wrapping",
        "Missing end-of-life guidance",
        "APAC",
        "Packaging",
        "Disposal and recycling instructions",
        "Freetext",
        "",
        "Missing",
        "Separate paper sleeve from plastic insert before recycling",
    ),
    (
        "Reed Controls",
        "Outdated certificate expiry",
        "LATAM",
        "Electronics",
        "Environmental certificate valid until",
        "Date",
        "2026-03-31",
        "Outdated",
        "2028-09-30",
    ),
    (
        "Spruce Fibres",
        "Origin claim needs clarification",
        "AMER",
        "Textiles",
        "Fibre origin statement",
        "Freetext",
        "Two origin declarations conflict",
        "Flagged (needs supplier confirmation)",
        "Cotton sourced from Portugal for this demonstration batch",
    ),
    (
        "Willow Systems",
        "Missing maintenance instructions",
        "APAC",
        "Industrial",
        "Maintenance interval",
        "Freetext",
        "",
        "Missing",
        "Inspect every 6 months and replace the filter annually",
    ),
]


# Deliberately shuffled so neighboring suppliers have visibly different workloads.
OUTSTANDING_COUNTS = [1, 5, 12, 3, 20, 8, 2, 15, 4, 10, 6, 18, 7, 14, 9, 16, 11, 19, 13, 17]
COMMON_QUESTIONS = [
    ("Product revision reference", "Revision B, demonstration release 2026", "Product identity"),
    ("Production batch reference", "Fictional batch DEMO-2026-09", "Traceability"),
    ("Declared functional unit", "One finished product", "Product identity"),
    ("Assessment reference period", "January to December 2026", "Environmental data"),
    ("Electricity use per unit", "2.4 kWh per unit", "Energy"),
    ("Renewable electricity share", "65 percent", "Energy"),
    ("Waste generated per unit", "0.08 kg per unit", "Environmental data"),
    ("Main delivery distance", "450 km", "Logistics"),
    ("Shipment loading assumption", "80 percent load factor", "Logistics"),
    ("Reusable transport packaging", "Reusable crates for return shipments", "Packaging"),
    ("Evidence issue date", "2026-09-01", "Evidence"),
    ("Data measurement approach", "Measured site totals allocated per product", "Evidence"),
]
INDUSTRY_QUESTIONS = {
    "Automotive": [
        ("Part drawing revision", "Drawing DEMO-A revision 3", "Engineering"),
        ("Vehicle application", "Fictional electric passenger vehicle", "Engineering"),
        ("Component surface treatment", "Water-based protective coating", "Materials"),
        ("Assembly joining method", "Mechanical fasteners", "Manufacturing"),
        ("Service replacement interval", "Inspect after 60000 km", "Maintenance"),
        ("Remanufacturing suitability", "Housing suitable for remanufacturing", "Circularity"),
    ],
    "Packaging": [
        ("Board thickness", "1.2 mm", "Packaging specifications"),
        ("Packaging layer count", "Three layers", "Packaging specifications"),
        ("Printing ink system", "Water-based ink", "Materials"),
        ("Adhesive type", "Starch-based adhesive", "Materials"),
        ("Reusable packaging cycles", "20 cycles under normal use", "Circularity"),
        ("Flattened storage dimensions", "400 by 300 by 20 mm", "Logistics"),
    ],
    "Electronics": [
        ("Standby power consumption", "0.4 W", "Electrical specifications"),
        ("Rated operating voltage", "24 V DC", "Electrical specifications"),
        ("Printed circuit board layers", "Four layers", "Materials"),
        ("Battery replacement approach", "Replaceable battery module", "Repairability"),
        ("Firmware support period", "Five years after delivery", "Product support"),
        ("Electronic waste handling", "Return through dedicated electronics collection", "Circularity"),
    ],
    "Textiles": [
        ("Fabric area weight", "180 g per square metre", "Textile specifications"),
        ("Fabric construction", "Plain weave", "Textile specifications"),
        ("Dyeing process", "Low-temperature batch dyeing", "Manufacturing"),
        ("Washing instructions", "Machine wash at 30 degrees Celsius", "Product care"),
        ("Finishing treatment", "Mechanical softening", "Manufacturing"),
        ("Cutting waste recovery", "Offcuts collected for fibre recycling", "Circularity"),
    ],
    "Industrial": [
        ("Rated operating power", "1.5 kW", "Technical specifications"),
        ("Lubricant specification", "Synthetic lubricant grade DEMO-46", "Maintenance"),
        ("Replacement parts availability", "Seven years after delivery", "Product support"),
        ("Operating temperature range", "5 to 40 degrees Celsius", "Technical specifications"),
        ("Installation requirements", "Level indoor surface with grounded power", "Installation"),
        ("Disassembly approach", "Remove bolted panels before separating modules", "Circularity"),
    ],
}


def generate():
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / "replies").mkdir(exist_ok=True)
    rows, manifest = [], []
    for i, (name, reason, region, industry, label, kind, old, status, answer) in enumerate(SUPPLIERS, 1):
        sid = f"DEMO20-{i:02d}"
        fields = [
            (label, kind, old, status, answer),
            (
                "Supporting evidence reference",
                "Freetext",
                "",
                "Missing",
                f"Fictional demo evidence {sid}, reporting period 2026",
            ),
            (
                "Product family confirmation",
                "Freetext",
                f"Demo product family {i:02d}",
                "Complete",
                f"Demo product family {i:02d}",
            ),
        ]
        target = OUTSTANDING_COUNTS[i - 1]
        categories = {1: "Supplier-specific request", 2: "Evidence", 3: "Product identity"}
        if target == 1:
            label2, type2, _, _, answer2 = fields[1]
            fields[1] = (label2, type2, answer2, "Complete", answer2)
        questions = INDUSTRY_QUESTIONS[industry] + COMMON_QUESTIONS
        for offset, (question, response, category) in enumerate(questions[: max(0, target - 2)], 4):
            field_status = ["Missing", "Outdated", "Flagged (needs supplier confirmation)"][(offset - 4) % 3]
            previous = (
                "" if field_status == "Missing" else "Previous demonstration value; supplier update required"
            )
            fields.append(
                (
                    question,
                    "Date" if question == "Evidence issue date" else "Freetext",
                    previous,
                    field_status,
                    response,
                )
            )
            categories[offset] = category
        reply = [f"Hello NOVA team,\n\nHere are the answers from Demo {name}:\n"]
        for j, (field_label, field_type, previous, field_status, value) in enumerate(fields, 1):
            fid = f"{sid}-F{j}"
            rows.append(
                dict(
                    zip(
                        CSV_COLUMNS,
                        [
                            fid,
                            sid,
                            f"Demo {name}",
                            f"{sid}-ARTICLE",
                            "MDF",
                            "DEMO",
                            categories[j],
                            reason if j <= 3 else categories[j],
                            field_label,
                            field_type,
                            "Yes",
                            "yes",
                            previous,
                            "2025-01-15" if previous else "",
                            field_status,
                        ],
                    )
                )
                | {"Region": region, "Industry": industry}
            )
            reply.append(f"{fid}={value}")
        reply.append(
            "\nThese are fictional demonstration values.\nKind regards,\nAlex Example\nDemo supplier representative\n"
        )
        (DEST / "replies" / f"{sid}.txt").write_text("\n".join(reply))
        manifest.append(
            {
                "supplier_id": sid,
                "name": f"Demo {name}",
                "reason": reason,
                "region": region,
                "industry": industry,
                "expected_primary_value": answer,
                "outstanding_count": target,
                "field_count": len(fields),
            }
        )
    with (DEST / "suppliers.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS + ["Region", "Industry"])
        writer.writeheader()
        writer.writerows(rows)
    parsed = parse_csv((DEST / "suppliers.csv").read_bytes())
    assert len(parsed) == 231 and len({r["Supplier ID"] for r in parsed}) == 20
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    guide = [
        "# Colleague demonstration: 20 fictional suppliers",
        "",
        "Open https://nova-bnw6dmyvva-ey.a.run.app and sign in using the reviewer access key.",
        "Search **DEMO20** to show exactly these 20 suppliers. Outstanding workloads range from 1 to 20 fields",
        "with existing values to demonstrate unchanged confirmations.",
        "",
        "## Five-minute walkthrough",
        "",
        "1. Show the supplier list, then open **Demo Alder Motion** (DEMO20-01).",
        "2. Review the one missing certificate expiry; compare with Demo Ember Components, which has 20 outstanding fields.",
        "3. Open the **Email** tab. The request is prepared for the configured test mailbox.",
        "   Click **Approve email & send** when ready. This sends one real demo email.",
        "4. In that mailbox, reply to the request, preserving the entire subject.",
        "   Paste [the prepared reply](replies/DEMO20-01.txt). Sending and receiving use the same test mailbox.",
        "5. Gmail push triggers n8n and NOVA. Refresh NOVA after extraction completes.",
        "6. Open **Supplier review**: show the original reply and all three proposals.",
        "   Expected expiry: **2028-12-31**; the product family is an unchanged confirmation.",
        "7. Approve the values, then mark the entire reply reviewed to complete the case.",
        "",
        "All 20 request drafts await human approval. Preparing this dataset does not send emails.",
        "Use each supplier's reply file for the corresponding email; the subject routes it to the right case.",
        "Original supplier records and replies remain in Cloud SQL; Anymize runs before Gemini extraction.",
        "",
        "## Supplier list",
        "",
        "| ID | Supplier | Region / industry | Outstanding | Reason to contact |",
        "|---|---|---|---|---|",
    ]
    for item in manifest:
        guide.append(
            f"| {item['supplier_id']} | {item['name']} | {item['region']} / {item['industry']} | {item['outstanding_count']} | {item['reason']} |"
        )
    guide += [
        "",
        "## Industry and categories",
        "",
        "Industry and region filter suppliers using imported metadata. Category applicability is not inferred by the agent.",
        "This demo explicitly seeds industry-specific questions plus shared product, evidence, energy and logistics categories.",
        "For example, electronics includes standby power and circuit boards; textiles includes fabric and dyeing questions.",
        "",
        "## Reuse",
        "",
        "Run `uv run python -m scripts.prepare_colleague_demo --load` from the configured project workspace.",
        "The loader preserves existing cases, records its import ID before approval, and never approves email sending.",
        "It skips already existing demo suppliers; it does not reset completed cases.",
        "The CSV, manifest and 20 reply files are versioned together. All names and values are fictional.",
        "",
    ]
    (DEST / "README.md").write_text("\n".join(guide))
    print("Generated 20 suppliers, 231 fields (210 outstanding) and 20 matching reply examples.", flush=True)
    return manifest


def load(manifest):
    urls = json.loads((ROOT / "urls.json").read_text())
    state_path = ROOT / "colleague-demo.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    ids = {s["supplier_id"] for s in manifest}
    with httpx.Client(
        base_url=urls["nova"],
        headers={"Authorization": "Bearer " + values()["NOVA_REVIEWER_TOKEN"]},
        timeout=60,
    ) as client:

        def api(method, path, **kwargs):
            result = client.request(method, path, **kwargs)
            if not result.is_success:
                raise RuntimeError(f"Demo setup {method} {path}: HTTP {result.status_code}")
            return result.json()

        config = api("GET", "/configuration")
        existing = api("GET", "/cases", params={"limit": 500})
        present = {c["supplier_id"] for c in existing} & ids
        if not present:
            if "import_id" not in state:
                batch = api(
                    "POST",
                    "/imports",
                    files={"file": ("colleague-demo.csv", (DEST / "suppliers.csv").read_bytes())},
                )
                state["import_id"] = batch["id"]
                save(state_path, state)
            api(
                "POST",
                f"/imports/{state['import_id']}/approve",
                json={"contacts": {sid: config["gmail_supplier"] for sid in ids}},
            )
        elif present != ids:
            raise RuntimeError("Partial demo ID collision: inspect existing demo cases before loading")
        cases = [c for c in api("GET", "/cases", params={"limit": 500}) if c["supplier_id"] in ids]
        assert len(cases) == 20
        report = []
        for case in cases:
            assert case["recipient"] == config["gmail_supplier"]
            detail = api("GET", "/cases/" + case["id"])
            assert len(detail["fields"]) == next(
                s["field_count"] for s in manifest if s["supplier_id"] == case["supplier_id"]
            )
            drafts = api("GET", "/drafts", params={"case_id": case["id"]})
            if not drafts and case["status"] == "open":
                api("POST", f"/cases/{case['id']}/draft")
            report.append({"supplier_id": case["supplier_id"], "case_id": case["id"]})
        state.update(
            cases=report, supplier_count=20, field_count=sum(s["field_count"] for s in manifest), loaded=True
        )
        save(state_path, state)
        final = [c for c in api("GET", "/cases", params={"limit": 500}) if c["supplier_id"] in ids]
        print(
            "Cloud demo loaded:",
            len(final),
            "suppliers;",
            sum(c["outstanding_count"] for c in final),
            "outstanding fields.",
            flush=True,
        )
        print("Request review ready:", sum(c["status"] == "email_review" for c in final), flush=True)
        print("Find the demonstration by searching DEMO20 in NOVA.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load", action="store_true")
    args = parser.parse_args()
    manifest = generate()
    if args.load:
        load(manifest)
