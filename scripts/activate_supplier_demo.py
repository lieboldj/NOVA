"""Deploy the approved 4418 demo and send its twenty requests through approval-gated NOVA."""

import argparse
import json
import re
from pathlib import Path

import httpx

from nova.demo_replies import DEMO_MAILBOX
from scripts.deploy_cloud import REGION, ROOT, gc, save, values


def deploy():
    image = json.loads((ROOT / "images.json").read_text())["nova"]
    for service in ("nova", "nova-worker"):
        gc(
            "run",
            "services",
            "update",
            service,
            f"--region={REGION}",
            f"--image={image}",
            f"--update-env-vars=GMAIL_SUPPLIER={DEMO_MAILBOX},DEMO_AUTO_REPLY=true",
        )
        print(service + ": updated for 4418 and labelled demo responses", flush=True)
    path = Path(".env")
    content = path.read_text()
    for key, value in {"GMAIL_SUPPLIER": DEMO_MAILBOX, "DEMO_AUTO_REPLY": "true"}.items():
        content = (
            re.sub(r"^" + key + "=.*$", key + "=" + value, content, flags=re.M)
            if re.search(r"^" + key + "=", content, re.M)
            else content + "\n" + key + "=" + value + "\n"
        )
    path.write_text(content)
    path = ROOT / "nova-env.json"
    env = json.loads(path.read_text())
    env.update(GMAIL_SUPPLIER=DEMO_MAILBOX, DEMO_AUTO_REPLY="true")
    save(path, env)


def send():
    urls = json.loads((ROOT / "urls.json").read_text())
    state_path = ROOT / "supplier-4418-demo.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    with httpx.Client(
        base_url=urls["nova"],
        headers={"Authorization": "Bearer " + values()["NOVA_REVIEWER_TOKEN"]},
        timeout=60,
    ) as client:

        def api(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if not response.is_success:
                raise RuntimeError(f"{method} {path} returned HTTP {response.status_code}")
            return response.json()

        configuration = api("GET", "/configuration")
        assert configuration["gmail_supplier"] == DEMO_MAILBOX and configuration["demo_auto_reply"]
        cases = sorted(
            [
                c
                for c in api("GET", "/cases", params={"limit": 500})
                if re.fullmatch(r"DEMO20-(?:0[1-9]|1[0-9]|20)", c["supplier_id"])
            ],
            key=lambda c: c["supplier_id"],
        )
        assert len(cases) == 20
        for case in cases:
            drafts = api("GET", "/drafts", params={"case_id": case["id"]})
            delivered = [
                d
                for d in drafts
                if d["recipient"] == DEMO_MAILBOX
                and d["status"] in ("approved", "sending", "sent", "uncertain")
            ]
            if delivered:
                if any(d["status"] == "uncertain" for d in delivered):
                    raise RuntimeError("An uncertain 4418 delivery needs reconciliation before proceeding")
                state[case["supplier_id"]] = {"case_id": case["id"], "draft_id": delivered[0]["id"]}
                save(state_path, state)
                continue
            if case["recipient"] != DEMO_MAILBOX:
                case = api(
                    "POST",
                    f"/cases/{case['id']}/contact/approve",
                    json={"revision": case["revision"], "recipient": DEMO_MAILBOX},
                )
            draft = api("POST", f"/cases/{case['id']}/draft")
            assert draft["status"] == "pending" and draft["recipient"] == DEMO_MAILBOX
            footer = "\n\nFictional NOVA demo: this request is real; sample supplier responses will be simulated inside NOVA. No action is required from this test mailbox."
            if footer not in draft["body"]:
                draft = api(
                    "PATCH",
                    "/drafts/" + draft["id"],
                    json={
                        "version": draft["version"],
                        "subject": draft["subject"],
                        "body": draft["body"] + footer,
                    },
                )
            state[case["supplier_id"]] = {"case_id": case["id"], "draft_id": draft["id"]}
            save(state_path, state)
            # Explicit user instruction authorizes sending this concrete set of demo requests.
            api("POST", "/drafts/" + draft["id"] + "/approve", json={"version": draft["version"]})
            print(case["supplier_id"] + ": approved for real delivery to 4418", flush=True)
    print(
        "Twenty demo requests are authorized; the cloud worker sends and generates labelled responses.",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["deploy", "send"])
    globals()[parser.parse_args().phase]()
