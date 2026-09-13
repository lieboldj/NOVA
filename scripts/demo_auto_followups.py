"""Create three isolated fictional cases and verify real automatic follow-up delivery."""

import argparse
import csv
import io
import json

import httpx

from nova.demo_replies import AUTO_ANSWERS
from nova.followups import AI_DISCLOSURE
from nova.workflow import CSV_COLUMNS
from scripts.deploy_cloud import ROOT, save, values

SCENARIOS = {"PARTIAL": [5, 6], "EMPTY": [1, 2, 3, 4, 5, 6], "INVALID": [2]}


def main(phase):
    urls = json.loads((ROOT / "urls.json").read_text())
    path = ROOT / "auto-followup-demo.json"
    state = json.loads(path.read_text()) if path.exists() else {}
    with httpx.Client(
        base_url=urls["nova"],
        headers={"Authorization": "Bearer " + values()["NOVA_REVIEWER_TOKEN"]},
        timeout=60,
    ) as client:

        def api(method, url, **kwargs):
            r = client.request(method, url, **kwargs)
            if not r.is_success:
                raise RuntimeError(f"{method} {url} returned HTTP {r.status_code}")
            return r.json()

        config = api("GET", "/configuration")
        assert config["auto_followup_enabled"] and config["demo_auto_reply"]
        for scenario, expected in SCENARIOS.items():
            sid = "DEMO-AUTO-" + scenario
            name = "Demo Auto " + scenario.title()
            cases = [c for c in api("GET", "/cases", params={"limit": 500}) if c["supplier_id"] == sid]
            if phase == "start" and not cases:
                rows = []
                for i, (label, kind, value) in enumerate(AUTO_ANSWERS, 1):
                    row = dict.fromkeys(CSV_COLUMNS, "")
                    row.update(
                        {
                            "Row ID": f"{sid}-F{i}",
                            "Supplier ID": sid,
                            "Supplier Name": name,
                            "NART": sid + "-ARTICLE",
                            "Use case": "MDF",
                            "Module (ID)": "DEMO",
                            "Category": "Automatic follow-up demonstration",
                            "Section": scenario.title(),
                            "Field (label)": label,
                            "Field Type": kind,
                            "Required @ go-live": "Yes",
                            "Editable by supplier": "yes",
                            "Status": "Missing",
                        }
                    )
                    rows.append(row)
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
                item = state.setdefault(sid, {})
                if "import_id" not in item:
                    item["import_id"] = api(
                        "POST", "/imports", files={"file": (sid + ".csv", output.getvalue())}
                    )["id"]
                    save(path, state)
                api(
                    "POST",
                    "/imports/" + item["import_id"] + "/approve",
                    json={"contacts": {sid: config["gmail_supplier"]}},
                )
                cases = [c for c in api("GET", "/cases", params={"limit": 500}) if c["supplier_id"] == sid]
            if not cases:
                raise RuntimeError("Start the demonstration first")
            case = cases[0]
            item = state.setdefault(sid, {})
            item["case_id"] = case["id"]
            drafts = api("GET", "/drafts", params={"case_id": case["id"]})
            if phase == "start":
                initial = next((d for d in drafts if d["kind"] == "request"), None)
                initial = initial or api("POST", "/cases/" + case["id"] + "/draft")
                item["initial_draft_id"] = initial["id"]
                save(path, state)
                if initial["status"] == "pending":
                    # This bounded live demonstration is explicitly authorized in the task.
                    api("POST", "/drafts/" + initial["id"] + "/approve", json={"version": initial["version"]})
                print(sid + ": initial demo request queued; follow-up must be policy-authorized.", flush=True)
            else:
                automatic = [d for d in drafts if d["kind"] == "auto_followup"]
                messages = api("GET", "/cases/" + case["id"] + "/messages")
                proposals = api("GET", "/proposals", params={"case_id": case["id"]})
                complete = (
                    len(automatic) == 1
                    and automatic[0]["status"] == "sent"
                    and len(messages) == 2
                    and all(m["status"] in ("evaluated", "needs_review") for m in messages)
                )
                if automatic:
                    auto = automatic[0]
                    assert auto["approved_by"] == "auto-followup"
                    assert auto["requested_fields"] == [f"{sid}-F{i}" for i in expected]
                    assert auto["body"].endswith("Thank you,\nSupplier Information Team\n\n" + AI_DISCLOSURE)
                detail = api("GET", "/cases/" + case["id"])
                assert all(f["data"]["Value submitted"] == "" for f in detail["fields"])
                assert all(p["status"] == "pending" for p in proposals)
                item.update(
                    complete=complete,
                    automatic_count=len(automatic),
                    proposals=len(proposals),
                    message_statuses=[m["status"] for m in messages],
                )
                print(
                    sid
                    + ": "
                    + json.dumps(
                        {k: item[k] for k in ("complete", "automatic_count", "proposals", "message_statuses")}
                    ),
                    flush=True,
                )
            save(path, state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["start", "check"])
    main(parser.parse_args().phase)
