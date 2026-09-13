"""Send one fictional self-mail and prove a production push execution synced its Gmail ID."""

import base64
import json
import time
from email.message import EmailMessage

import httpx

from nova.config import Settings
from nova.gmail import ROOT as GMAIL_ROOT
from nova.gmail import Gmail
from scripts.deploy_cloud import ROOT, save, values


def main():
    vals = values()
    urls = json.loads((ROOT / "urls.json").read_text())
    state = json.loads((ROOT / "n8n-setup.json").read_text())
    report_path = ROOT / "gmail-push-test.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    with httpx.Client(base_url=urls["n8n"], timeout=60) as client:
        response = client.post(
            "/rest/login",
            json={"emailOrLdapLoginId": "devstar4415@gcplab.me", "password": vals["N8N_OWNER_PASSWORD"]},
        )
        assert response.status_code == 200
        workflow = client.get("/rest/workflows/" + state["sync-gmail.json"]).json()["data"]
        assert workflow["active"]
        assert any(n["type"] == "n8n-nodes-base.webhook" for n in workflow["nodes"])
        assert all(
            n["parameters"]["rule"]["interval"][0].get("minutesInterval") != 1
            for n in workflow["nodes"]
            if n["type"] == "n8n-nodes-base.scheduleTrigger"
        )
        assert httpx.post(urls["nova"] + "/mail/gmail/push", json={}).status_code == 401
        assert httpx.post(urls["n8n"] + "/webhook/nova-gmail-push", json={}).status_code in (401, 403)
        if "gmail_id" not in report:
            if report.get("send_attempted"):
                raise RuntimeError("Previous send uncertain: reconcile mailbox before retrying")
            settings = Settings(**{k.lower(): v for k, v in vals.items() if k.startswith("GMAIL_")})
            with Gmail(settings) as gmail:
                gmail.authorize()
                mail = EmailMessage()
                mail["From"] = mail["To"] = settings.gmail_mailbox
                mail["Subject"] = "NOVA fictional Gmail push delivery test"
                mail.set_content("Technical demo notification test. No supplier data; no response needed.")
                report["send_attempted"] = True
                report["sent_at"] = time.time()
                save(report_path, report)
                response = gmail.http.post(
                    GMAIL_ROOT + "/messages/send",
                    headers={"Authorization": "Bearer " + gmail.token},
                    json={"raw": base64.urlsafe_b64encode(mail.as_bytes()).decode()},
                )
                if response.status_code != 200:
                    raise RuntimeError(f"Test send failed: HTTP {response.status_code}")
                report["gmail_id"] = response.json()["id"]
                save(report_path, report)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            response = client.get(
                "/rest/executions", params={"filter": json.dumps({"workflowId": workflow["id"]}), "limit": 30}
            )
            assert response.status_code == 200
            result = response.json()["data"]
            executions = result["results"] if isinstance(result, dict) else result
            for item in executions:
                if item.get("status") != "success" or item.get("mode") != "webhook":
                    continue
                execution = client.get("/rest/executions/" + item["id"]).json()["data"]
                detail = execution.get("data", {})
                # n8n stores execution data in its serialized form in some versions.
                if report["gmail_id"] in json.dumps(detail):
                    report.update(
                        passed=True,
                        execution_id=item["id"],
                        mode=item["mode"],
                        observed_seconds=round(time.time() - report["sent_at"], 1),
                    )
                    save(report_path, report)
                    print(
                        f"Actual Gmail push -> n8n -> NOVA sync: PASS ({report['observed_seconds']} seconds)"
                    )
                    return
            time.sleep(3)
        raise RuntimeError("No successful production webhook execution contained the test Gmail ID")


if __name__ == "__main__":
    main()
