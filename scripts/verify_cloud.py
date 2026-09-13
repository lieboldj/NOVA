"""Read-only access checks plus safe manual executions of the deployed scheduler workflows."""

import json
import time

import httpx

from scripts.deploy_cloud import REGION, ROOT, gc, save, values


def main():
    urls = json.loads((ROOT / "urls.json").read_text())
    state = json.loads((ROOT / "n8n-setup.json").read_text())
    vals = values()
    report = {"urls": urls}
    with httpx.Client(base_url=urls["nova"], timeout=60) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/cases").status_code == 401
        response = client.post(
            "/api/session", headers={"Origin": urls["nova"]}, json={"token": vals["NOVA_REVIEWER_TOKEN"]}
        )
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert all(flag in cookie for flag in ["httponly", "secure", "samesite=strict"])
        assert client.post("/api/automation/tick").status_code == 403
        cases = client.get("/api/cases").json()
        report["main_case_count"] = len(cases)
        report["gmail_connected"] = client.get("/api/mail/gmail/status").json()["connected"]
        assert report["gmail_connected"]
        report["https_login_and_csrf"] = True
    worker = gc(
        "run", "services", "describe", "nova-worker", f"--region={REGION}", "--format=value(status.url)"
    ).stdout.strip()
    report["worker_private"] = httpx.get(worker + "/health").status_code == 403
    assert report["worker_private"]
    with httpx.Client(base_url=urls["n8n"], timeout=60) as client:
        assert client.get("/rest/workflows").status_code == 401
        response = client.post(
            "/rest/login",
            json={
                "emailOrLdapLoginId": "devstar4415@gcplab.me",
                "password": vals["N8N_OWNER_PASSWORD"],
            },
        )
        assert response.status_code == 200
        report["n8n_owner_login"] = True
        report["workflows"] = []
        names = ["check-pending-cases.json", "sync-gmail.json"]
        if "renew-gmail-watch.json" in state:
            names.append("renew-gmail-watch.json")
        for name in names:
            workflow = client.get("/rest/workflows/" + state[name]).json()["data"]
            assert workflow["active"]
            trigger = next(n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.scheduleTrigger")
            response = client.post(
                f"/rest/workflows/{workflow['id']}/run",
                json={
                    "triggerToStartFrom": {"name": trigger["name"]},
                },
            )
            assert response.status_code == 200, (
                f"Manual scheduler execution failed: HTTP {response.status_code}"
            )
            result = response.json()["data"]
            execution_id = result["executionId"]
            deadline = time.monotonic() + 120
            while True:
                execution = client.get(f"/rest/executions/{execution_id}").json()["data"]
                if execution["status"] == "success":
                    break
                if execution["status"] in ["error", "crashed", "canceled"] or time.monotonic() > deadline:
                    raise RuntimeError(
                        f"Workflow {name} did not complete successfully; inspect n8n execution {execution_id}"
                    )
                time.sleep(2)
            report["workflows"].append(
                {
                    "name": workflow["name"],
                    "id": workflow["id"],
                    "active": True,
                    "verified_execution_id": execution_id,
                    "status": "success",
                }
            )
            print("Verified n8n execution:", workflow["name"], flush=True)
    report["cloud_email_test_passed"] = json.loads((ROOT / "smoke-result.json").read_text())["passed"]
    save(ROOT / "verification.json", report)
    print("Cloud authentication, worker privacy, Gmail and all configured n8n workflows: PASS", flush=True)
    print("Main database case count:", report["main_case_count"], flush=True)


if __name__ == "__main__":
    main()
