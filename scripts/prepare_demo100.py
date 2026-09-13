"""Generate a deterministic, entirely fictional scale fixture. No API calls or imports."""

import csv
from collections import Counter
from pathlib import Path

from nova.workflow import OUTSTANDING, V2_COLUMNS, parse_csv
from scripts.prepare_colleague_demo import COMMON_QUESTIONS, INDUSTRY_QUESTIONS

DEST = Path("examples/colleague-demo/demo100")
ROOTS = [
    "Alderhaven",
    "Briarvale",
    "Cindermere",
    "Dunewick",
    "Emberbrook",
    "Fernbridge",
    "Glenwick",
    "Hazelreach",
    "Ivoryfen",
    "Junipercrest",
]
BUSINESSES = [
    ("Motion Works", "Automotive"),
    ("Fibre Packs", "Packaging"),
    ("Signal Devices", "Electronics"),
    ("Woven Materials", "Textiles"),
    ("Process Systems", "Industrial"),
    ("Drive Components", "Automotive"),
    ("Circular Cartons", "Packaging"),
    ("Sensor Assemblies", "Electronics"),
    ("Technical Fabrics", "Textiles"),
    ("Precision Tools", "Industrial"),
]
LOCATIONS = [
    ("Germany", "EMEA"),
    ("France", "EMEA"),
    ("Poland", "EMEA"),
    ("Portugal", "EMEA"),
    ("Sweden", "EMEA"),
    ("United States", "AMER"),
    ("Canada", "AMER"),
    ("Mexico", "LATAM"),
    ("Brazil", "LATAM"),
    ("Chile", "LATAM"),
    ("Japan", "APAC"),
    ("South Korea", "APAC"),
    ("India", "APAC"),
    ("Vietnam", "APAC"),
    ("Australia", "APAC"),
    ("South Africa", "EMEA"),
    ("Turkey", "EMEA"),
    ("Malaysia", "APAC"),
    ("Thailand", "APAC"),
    ("Spain", "EMEA"),
]


def generate():
    DEST.mkdir(parents=True, exist_ok=True)
    rows, manifest = [], []
    for index in range(100):
        sid = f"DEMO100-{index + 1:03d}"
        suffix, industry = BUSINESSES[index % 10]
        name = f"Demo {ROOTS[index // 10]} {suffix}"
        country, region = LOCATIONS[(index * 7 + index // 10) % len(LOCATIONS)]
        questions = (
            [
                (label, value, section, "MDF", "DEMO100-M1", industry)
                for label, value, section in INDUSTRY_QUESTIONS[industry]
            ]
            + [
                (label, value, section, "PCF", "DEMO100-M2", "Product footprint and logistics")
                for label, value, section in COMMON_QUESTIONS
            ]
            + [
                (
                    "Quality certificate valid until",
                    "2028-12-31",
                    "Quality evidence",
                    "MDF",
                    "DEMO100-M3",
                    "Quality",
                ),
                (
                    "Reporting year",
                    "2026",
                    "Reporting period",
                    "PCF",
                    "DEMO100-M2",
                    "Product footprint and logistics",
                ),
                (
                    "Product family confirmation",
                    f"Fictional {industry.lower()} family {index + 1}",
                    "Identity",
                    "MDF",
                    "DEMO100-M1",
                    industry,
                ),
                (
                    "Demo applicability note",
                    "Not applicable to this fictional product",
                    "Applicability",
                    "MDF",
                    "DEMO100-M3",
                    "Quality",
                ),
            ]
        )
        for article in range(1, 4):
            nart = f"{sid}-A{article:02d}"
            count = (index * 7 + (article - 1) * 9) % 20 + 1
            for q, (label, answer, section, use_case, module, category) in enumerate(questions):
                field_type = (
                    "Date"
                    if label in ("Quality certificate valid until", "Evidence issue date")
                    else "Freetext"
                )
                status = (
                    ["Missing", "Outdated", "Flagged (needs supplier confirmation)"][
                        (index + article + q) % 3
                    ]
                    if q < count
                    else "Complete"
                )
                value = answer
                if status == "Missing":
                    value = ""
                elif status == "Outdated":
                    value = (
                        "2024-06-30"
                        if field_type == "Date"
                        else "2024"
                        if label == "Reporting year"
                        else f"2024 declaration: {answer}"
                    )
                elif status.startswith("Flagged"):
                    value = (
                        answer
                        if field_type == "Date" or label == "Reporting year"
                        else f"Unverified declaration: {answer}"
                    )
                if q == len(questions) - 1:
                    status = "N/A (informational field)"
                row = dict.fromkeys(V2_COLUMNS, "")
                row.update(
                    {
                        "Row ID": f"{nart}-F{q + 1:02d}",
                        "Supplier ID": sid,
                        "Supplier Name": name,
                        "Country": country,
                        "NART": nart,
                        "Use case": use_case,
                        "Module (ID)": module,
                        "Category": category,
                        "Section": section,
                        "Field (label)": label,
                        "Field Type": field_type,
                        "Required @ go-live": "No" if status.startswith("N/A") else "Yes",
                        "Editable by supplier": "no" if status.startswith("N/A") else "yes",
                        "Value submitted": value,
                        "Submission date": ""
                        if not value
                        else "2024-06-30"
                        if status == "Outdated"
                        else "2026-09-01",
                        "Status": status,
                        "Workflow status": "Open" if status in OUTSTANDING else "Closed",
                        "Last contact date": "" if index % 3 == 0 else f"2026-09-{1 + index % 10:02d}",
                        "Region": region,
                        "Industry": industry,
                    }
                )
                rows.append(row)
            manifest.append(
                {
                    "Supplier ID": sid,
                    "Supplier Name": name,
                    "Country": country,
                    "Region": region,
                    "Industry": industry,
                    "NART": nart,
                    "Outstanding fields": count,
                }
            )
    with (DEST / "suppliers.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=V2_COLUMNS + ["Region", "Industry"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    parse_csv((DEST / "suppliers.csv").read_bytes())
    with (DEST / "article-index.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(manifest[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest)
    print(
        {
            "suppliers": 100,
            "articles": len(manifest),
            "fields": len(rows),
            "statuses": dict(Counter(r["Status"] for r in rows)),
        }
    )


if __name__ == "__main__":
    generate()
