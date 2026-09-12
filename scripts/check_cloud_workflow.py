"""Run a real self-mail test on a separate Cloud SQL database and private Cloud Run services.

The main NOVA database stays empty. This sends one approved fictional request and one
fictional supplier reply, and leaves the resulting evidence/proposals for inspection.
Reusing its state file does not send another request or reply. Test services are removed
after verification; the isolated database is retained for repeatability and audit.
"""

import base64
import io
import json
import os
import time
from email.message import EmailMessage
from email.utils import make_msgid

import httpx
from reportlab.pdfgen.canvas import Canvas

from nova.config import get_settings
from nova.gmail import ROOT as GMAIL_ROOT
from nova.gmail import Gmail
from scripts.deploy_cloud import REGION, ROOT, SQL, gc, save, secret_name, service_account, values


def provision():
    vals = values()
    images = json.loads((ROOT / "images.json").read_text())
    if gc("sql", "databases", "describe", "nova_smoke", "--instance=nova-db", required=False).returncode:
        gc("sql", "databases", "create", "nova_smoke", "--instance=nova-db")
    secret = "nova-smoke-database-url"
    if gc("secrets", "describe", secret, required=False).returncode:
        gc("secrets", "create", secret, "--replication-policy=user-managed", f"--locations={REGION}")
        gc(
            "secrets",
            "versions",
            "add",
            secret,
            "--data-file=-",
            data=vals["DATABASE_URL"].replace("@/nova?", "@/nova_smoke?"),
        )
    gc(
        "secrets",
        "add-iam-policy-binding",
        secret,
        f"--member=serviceAccount:{service_account('nova-api')}",
        "--role=roles/secretmanager.secretAccessor",
    )
    gc(
        "run",
        "jobs",
        "deploy",
        "nova-smoke-migrate",
        f"--region={REGION}",
        f"--image={images['nova']}",
        f"--service-account={service_account('nova-api')}",
        f"--set-cloudsql-instances={SQL}",
        f"--set-secrets=DATABASE_URL={secret}:1",
        "--command=alembic",
        "--args=upgrade,head",
        "--tasks=1",
        "--max-retries=0",
        "--task-timeout=300s",
        "--memory=512Mi",
    )
    gc("run", "jobs", "execute", "nova-smoke-migrate", f"--region={REGION}", "--wait")
    keys = [
        "GEMINI_API_KEY",
        "ANYMIZE_API_KEY",
        "GMAIL_CLIENT_ID",
        "GMAIL_CLIENT_SECRET",
        "GMAIL_REFRESH_TOKEN",
    ]
    for name, worker in (("nova-smoke", False), ("nova-smoke-worker", True)):
        chosen = keys if worker else keys + ["NOVA_REVIEWER_TOKEN", "NOVA_AUTOMATION_TOKEN"]
        refs = ",".join([f"DATABASE_URL={secret}:1"] + [f"{k}={secret_name(k)}:1" for k in chosen])
        args = [
            "run",
            "deploy",
            name,
            f"--region={REGION}",
            f"--image={images['nova']}",
            f"--service-account={service_account('nova-api')}",
            f"--add-cloudsql-instances={SQL}",
            f"--env-vars-file={ROOT / 'nova-env.json'}",
            f"--set-secrets={refs}",
            "--port=8000",
            "--cpu=1",
            "--memory=512Mi",
            "--timeout=300s",
            "--max-instances=1",
            "--min-instances=1" if worker else "--min-instances=0",
            "--no-allow-unauthenticated",
        ]
        if worker:
            args += [
                "--no-cpu-throttling",
                "--command=uvicorn",
                "--args=nova.cloud_worker:app,--host,0.0.0.0,--port,8000",
            ]
        gc(*args)
    return gc(
        "run", "services", "describe", "nova-smoke", f"--region={REGION}", "--format=value(status.url)"
    ).stdout.strip()


def run(url):
    vals = values()
    state_path = ROOT / "smoke-result.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    headers = {
        "Authorization": "Bearer " + vals["NOVA_REVIEWER_TOKEN"],
        "X-Serverless-Authorization": "Bearer " + gc("auth", "print-identity-token").stdout.strip(),
    }
    with httpx.Client(base_url=url, headers=headers, timeout=180) as client:

        def api(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if not response.is_success:
                raise RuntimeError(f"NOVA smoke {method} {path}: HTTP {response.status_code}")
            return response.json()

        if "case_id" not in state:
            from pathlib import Path

            content = Path("examples/cloud-demo.csv").read_bytes()
            imported = api("POST", "/imports", files={"file": ("cloud-demo.csv", content)})
            state["case_id"] = api(
                "POST",
                f"/imports/{imported['id']}/approve",
                json={
                    "contacts": {"CLOUD-DEMO-SUPPLIER": get_settings().gmail_mailbox},
                },
            )["case_ids"][0]
            save(state_path, state)
        case_id = state["case_id"]
        if "draft_id" not in state:
            draft = api("POST", f"/cases/{case_id}/draft")
            draft = api(
                "PATCH",
                f"/drafts/{draft['id']}",
                json={
                    "version": draft["version"],
                    "subject": draft["subject"] + " TEST ONLY — cloud verification",
                    "body": "Fictional test only. No business action required.\n\n" + draft["body"],
                },
            )
            state["draft_id"] = draft["id"]
            save(state_path, state)
            api("POST", f"/drafts/{draft['id']}/approve", json={"version": draft["version"]})
        deadline = time.monotonic() + 180
        while True:
            draft = next(d for d in api("GET", f"/drafts?case_id={case_id}") if d["id"] == state["draft_id"])
            if draft["status"] == "sent":
                break
            if draft["status"] in ("uncertain", "rejected") or time.monotonic() > deadline:
                raise RuntimeError(
                    "Cloud request not confirmed sent; inspect the isolated jobs before retrying."
                )
            time.sleep(3)
        state["request_provider_id"] = draft["provider_id"]
        save(state_path, state)
        print("Cloud worker sent the approved request:", draft["provider_id"], flush=True)
        if "reply_status" not in state:
            message = EmailMessage()
            mailbox = get_settings().gmail_mailbox
            message["From"] = mailbox
            message["To"] = mailbox
            message["Subject"] = "Re: " + draft["subject"]
            message["Message-ID"] = make_msgid(domain="nova-test.invalid")
            message["In-Reply-To"] = f"<nova-{draft['id']}-v{draft['version']}@{mailbox.split('@')[1]}>"
            message["X-NOVA-Test-Reply"] = "fictional-cloud-verification"
            message.set_content(
                "TEST ONLY. I am Max Mustermann at Fictional Cloud Demo Ltd. "
                "Contact max.mustermann@example.com.\n"
                "CLOUD-DEMO-F1=80% recycled aluminium\n"
                "CLOUD-DEMO-F2=2028-12-31\n"
                "CLOUD-DEMO-F3=Renewable energy confirmed\n"
                "The certificate expires on 31 December 2028. Additional note: call us about packaging.\n"
            )
            stream = io.BytesIO()
            pdf = Canvas(stream)
            pdf.drawString(50, 750, "Fictional Cloud Demo Ltd — TEST ONLY")
            pdf.drawString(50, 720, "The certificate expires on 31 December 2028.")
            pdf.save()
            message.add_attachment(
                stream.getvalue(), maintype="application", subtype="pdf", filename="fictional-certificate.pdf"
            )
            with Gmail(get_settings()) as gmail:
                gmail.authorize()
                state["reply_status"] = "sending"
                save(state_path, state)
                # Never retry an ambiguous send. The state file requires reconciliation first.
                response = gmail.http.post(
                    GMAIL_ROOT + "/messages/send",
                    headers={"Authorization": "Bearer " + gmail.token},
                    json={"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()},
                )
                response.raise_for_status()
                state["reply_provider_id"] = response.json()["id"]
                state["reply_status"] = "sent"
                save(state_path, state)
        if state["reply_status"] != "sent":
            raise RuntimeError("Test reply sending outcome needs reconciliation; not resending.")
        deadline = time.monotonic() + 300
        while True:
            sync = api("POST", "/automation/gmail/sync")
            messages = api("GET", f"/cases/{case_id}/messages")
            if messages and all(m["status"] == "evaluated" for m in messages):
                break
            if (
                any(m["status"] in ("failed", "needs_review") for m in messages)
                or time.monotonic() > deadline
            ):
                raise RuntimeError("Cloud reply evaluation requires inspection; see isolated jobs.")
            time.sleep(5)
        assert len(messages) == 1, "Outgoing request must not be ingested as another reply"
        state["outgoing_request_skipped"] = any(
            r.get("status") == "outgoing_request" for r in sync["results"]
        )
        proposals = api("GET", f"/proposals?case_id={case_id}")
        assert {p["field_id"] for p in proposals} == {"CLOUD-DEMO-F1", "CLOUD-DEMO-F2", "CLOUD-DEMO-F3"}
        assert next(p for p in proposals if p["field_id"] == "CLOUD-DEMO-F2")["value"] == "2028-12-31"
        assert all(p["status"] == "pending" and not p["validation_errors"] for p in proposals)
        assert (
            next(p for p in proposals if p["field_id"] == "CLOUD-DEMO-F1")["old_value"]
            == "80% recycled aluminium"
        )
        attachment = messages[0]["documents"][0]
        assert client.get(f"/documents/{attachment['id']}").content.startswith(b"%PDF-")
        detail = api("GET", f"/cases/{case_id}")
        assert (
            next(f for f in detail["fields"] if f["id"] == "CLOUD-DEMO-F2")["data"]["Value submitted"] == ""
        )
        state.update(
            passed=True, proposals=proposals, messages=messages, jobs=api("GET", f"/jobs?case_id={case_id}")
        )
        save(state_path, state)
        print("Cloud Gmail → private storage → Anymize → Gemini → full supplier review: PASS", flush=True)


if __name__ == "__main__":
    os.umask(0o077)
    url = provision()
    run(url)
    for name in ("nova-smoke", "nova-smoke-worker"):
        gc("run", "services", "delete", name, f"--region={REGION}")
    print("Temporary test services removed; main NOVA database remains clean.", flush=True)
