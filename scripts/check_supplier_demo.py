"""Report real Gmail sends and cloud-simulated response extraction without exposing message content."""

import json
from collections import Counter

import httpx

from scripts.deploy_cloud import ROOT, save, values


def main():
    urls = json.loads((ROOT / "urls.json").read_text())
    state = json.loads((ROOT / "supplier-4418-demo.json").read_text())
    report = {
        "cases": [],
        "sent": 0,
        "responses": 0,
        "evaluated": 0,
        "proposals": 0,
        "corrections": 0,
        "documents": 0,
    }
    with httpx.Client(
        base_url=urls["nova"],
        headers={"Authorization": "Bearer " + values()["NOVA_REVIEWER_TOKEN"]},
        timeout=60,
    ) as client:

        def get(path, **kwargs):
            response = client.get(path, **kwargs)
            response.raise_for_status()
            return response.json()

        drafts = {d["id"]: d for d in get("/drafts")}
        jobs = get("/jobs")
        for sid, item in sorted(state.items()):
            draft = drafts[item["draft_id"]]
            assert draft["recipient"] == "devstar4418@gcplab.me"
            messages = get("/cases/" + item["case_id"] + "/messages")
            simulated = [m for m in messages if m["external_id"] == "demo-simulated:" + draft["id"]]
            proposals = get("/proposals", params={"case_id": item["case_id"]})
            proposals = [p for p in proposals if p["message_id"] in {m["id"] for m in simulated}]
            report["sent"] += draft["status"] == "sent" and bool(draft["provider_id"])
            report["responses"] += len(simulated)
            report["evaluated"] += sum(m["status"] == "evaluated" for m in simulated)
            report["proposals"] += len(proposals)
            report["corrections"] += sum(bool(p["evidence"].get("spelling_correction")) for p in proposals)
            report["documents"] += sum(len(m["documents"]) for m in simulated)
            targets = {draft["id"]} | {m["id"] for m in simulated}
            failures = [
                {"kind": j["kind"], "error": j["error"]}
                for j in jobs
                if j["target_id"] in targets and j["status"] == "failed"
            ]
            report["cases"].append(
                {
                    "supplier_id": sid,
                    "send_status": draft["status"],
                    "reply_status": [m["status"] for m in simulated],
                    "proposal_count": len(proposals),
                    "failures": failures,
                }
            )
        report["job_statuses"] = dict(
            Counter(j["status"] for j in jobs if j["target_id"] in {d["draft_id"] for d in state.values()})
        )
        report["complete"] = report["sent"] == report["responses"] == report["evaluated"] == 20
        save(ROOT / "supplier-4418-verification.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}), flush=True)
    for case in report["cases"]:
        if case["failures"]:
            print(json.dumps(case), flush=True)


if __name__ == "__main__":
    main()
