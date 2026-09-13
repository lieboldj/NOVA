"""Connect imported DEMO100 cases to the demo mailbox and prepare UNSENT reviewer drafts."""

import json

import httpx

from nova.demo_replies import DEMO_MAILBOX, demo100_answers
from scripts.deploy_cloud import ROOT, save, values


def main():
    url = json.loads((ROOT / "urls.json").read_text())["nova"]
    expected = demo100_answers()
    with httpx.Client(
        base_url=url + "/api",
        headers={"Authorization": "Bearer " + values()["NOVA_REVIEWER_TOKEN"]},
        timeout=60,
    ) as client:

        def api(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        config = api("GET", "/configuration")
        if (
            config["auto_send_followups"]
            or not config["demo_auto_reply"]
            or config["gmail_supplier"] != DEMO_MAILBOX
        ):
            raise RuntimeError(
                "Require manual sending, simulated replies and the existing demo test mailbox."
            )
        cases, offset = [], 0
        while True:
            page = api("GET", "/cases", params={"limit": 500, "offset": offset})
            cases.extend(
                c
                for c in page
                if c["nart"] in expected
                and c["supplier_id"] == c["nart"][:11]
                and c["supplier_name"].startswith("Demo ")
            )
            if len(page) < 500:
                break
            offset += len(page)
        if {c["nart"] for c in cases} != set(expected):
            raise RuntimeError("Import the complete DEMO100 CSV before preparing the demo.")
        if any(c["recipient"] and c["recipient"].casefold() != DEMO_MAILBOX for c in cases):
            raise RuntimeError("A DEMO100 case has a different contact; existing contacts were not changed.")
        prepared, skipped = [], []
        for case in cases:
            if not case["recipient"]:
                case = api(
                    "POST",
                    f"/cases/{case['id']}/contact/approve",
                    json={"revision": case["revision"], "recipient": DEMO_MAILBOX},
                )
            drafts = api("GET", "/drafts", params={"case_id": case["id"]})
            if case["last_sent_at"] or any(
                d["status"] in ("approved", "sending", "uncertain", "sent", "simulated") for d in drafts
            ):
                skipped.append(case["id"])
                continue
            draft = api("POST", f"/cases/{case['id']}/draft")
            if draft["status"] != "pending" or draft["approved_by"] or draft["kind"] != "request":
                raise RuntimeError("Expected a pending initial draft; no email approval was performed.")
            prepared.append(draft["id"])
            if len(prepared) % 25 == 0:
                print(
                    f"{len(prepared)} initial drafts ready for human review; none approved by this script.",
                    flush=True,
                )
        save(ROOT / "demo100-prepared.json", {"draft_ids": prepared, "skipped_case_ids": skipped})
        print(f"Ready: {len(prepared)} pending drafts. Existing active/sent cases skipped: {len(skipped)}.")


if __name__ == "__main__":
    main()
