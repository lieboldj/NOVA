"""Live fictional workflow check; --send-email authorizes one supplier test request.

Uses a separate persistent database. Reusing --output never sends a second request.
The reply is injected through NOVA's API, not sent from the supplier's Gmail account.
Use --sync-replies later to ingest a real reply into the same isolated case.
That mode only queues evaluation: real evidence must wait for the privacy gap to be resolved.
"""

import argparse
import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from nova.api import create_app
from nova.config import get_settings
from nova.db import make_engine
from nova.gmail import Gmail
from nova.providers import ProviderUnavailable
from nova.worker import run_once
from nova.workflow import CSV_COLUMNS

SUPPLIER = "Fictional Example Ltd"
SUPPLIER_ID = "SYNTHETIC-LIVE-001"
ARTICLE = "DEMO-LIVE-ARTICLE"
ROW = "LIVE-CERTIFICATE-001"
PERSON = "Max Mustermann"
CONTACT = "max.mustermann@example.com"


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def submission():
    row = dict.fromkeys(CSV_COLUMNS, "")
    row.update({
        "Row ID": ROW, "Supplier ID": SUPPLIER_ID, "Supplier Name": SUPPLIER,
        "NART": ARTICLE, "Use case": "MDF", "Module (ID)": "1", "Section": "Demo",
        "Field (label)": "Certificate valid until", "Field Type": "Date",
        "Required @ go-live": "Yes", "Editable by supplier": "yes", "Status": "Missing",
    })
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerow(row)
    return out.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--send-email", action="store_true")
    parser.add_argument("--sync-replies", action="store_true")
    args = parser.parse_args()
    if not args.send_email and not args.sync_replies:
        parser.error("Choose --send-email for a new run or --sync-replies for a later real reply")
    os.umask(0o077)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    settings = get_settings().model_copy(update={
        "database_url": f"sqlite:///{output / 'workflow.db'}",
        "storage_path": output / "documents",
    })
    if (settings.mail_mode, settings.ai_mode, settings.anonymizer_mode) != ("gmail", "gemini", "anymize"):
        raise SystemExit("This live check requires Gmail, Gemini, and Anymize modes.")
    report_path = output / "result.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "fictional_evidence": True,
        "reply_transport": "synthetic API ingestion; no supplier mailbox authentication",
        "privacy_requirement": "NOT MET: hosted Anymize receives free text and original OCR pages",
    }
    review = {"Authorization": "Bearer " + settings.nova_reviewer_token.get_secret_value()}
    automation = {"Authorization": "Bearer " + settings.nova_automation_token.get_secret_value()}
    engine = make_engine(settings.database_url)
    app = create_app(settings, engine)
    original_request, original_post = httpx.request, httpx.post
    run_label = "real-reply" if args.sync_replies else "fictional-reply"
    anymize_calls, gemini_calls = [], []

    def observe_anymize(method, url, **kwargs):
        if method == "POST" and url.endswith("/anonymize"):
            body = kwargs["json"]["text"]
            record = {
                "endpoint": url,
                "known_supplier_identifiers_present": [
                    value for value in (SUPPLIER, SUPPLIER_ID, ARTICLE, ROW, settings.gmail_supplier)
                    if value.casefold() in body.casefold()
                ],
                "unregistered_person_present": PERSON.casefold() in body.casefold(),
                "unregistered_email_present": CONTACT.casefold() in body.casefold(),
            }
            anymize_calls.append(record)
            if not args.sync_replies:
                save(output / "anymize-request-fictional.json", kwargs["json"])
        return original_request(method, url, **kwargs)

    def observe_gemini(url, **kwargs):
        if "generativelanguage.googleapis.com/" in url:
            payload = kwargs["json"]
            body = json.dumps(payload, ensure_ascii=False)
            # Decode the nested JSON text to inspect Unicode identities as well.
            evidence = json.loads(payload["contents"][0]["parts"][0]["text"])
            decoded = json.dumps(evidence, ensure_ascii=False).casefold()
            identifiers = (
                SUPPLIER, SUPPLIER_ID, ARTICLE, ROW, PERSON, CONTACT,
                settings.gmail_supplier, settings.gmail_mailbox, "private-supplier-certificate.pdf",
            )
            leaked = [value for value in identifiers if value.casefold() in decoded]
            gemini_calls.append({
                "endpoint": url, "seeded_identity_leaks": leaked,
                "payload_sha256": hashlib.sha256(body.encode()).hexdigest(),
            })
            if leaked:
                raise ProviderUnavailable("Live test blocked Gemini: a seeded identity survived sanitization.")
            if not args.sync_replies:
                save(output / "gemini-request-fictional.json", payload)
            return original_post(url, **kwargs)
        return original_post(url, **kwargs)

    with TestClient(app) as client:
        def api(method, path, **kwargs):
            response = client.request(method, path, headers=kwargs.pop("headers", review), **kwargs)
            response.raise_for_status()
            return response.json()

        if "case_id" not in report:
            if not args.send_email:
                raise SystemExit("No existing test case; run with --send-email first.")
            # Refuse to create another case if a previous run stopped before persisting its report.
            if api("GET", "/cases"):
                raise SystemExit("Existing test database without a report; inspect it before sending.")
            imported = api("POST", "/imports", files={"file": ("fictional.csv", submission())})
            case_id = api("POST", f"/imports/{imported['id']}/approve", json={
                "contacts": {SUPPLIER_ID: settings.gmail_supplier},
            })["case_ids"][0]
            report["case_id"] = case_id
            save(report_path, report)
            draft = api("POST", f"/cases/{case_id}/draft")
            draft = api("PATCH", f"/drafts/{draft['id']}", json={
                "version": draft["version"],
                "subject": draft["subject"] + " — TEST ONLY / fictional data",
                "body": "TEST ONLY — fictional supplier data, no business action required.\n\n"
                + draft["body"]
                + f"\n\nTo test a reply, keep this subject and reply with:\n"
                f"{ROW}=2028-12-31\nThe certificate expires on 31 December 2028.\n",
            })
            save(output / "approved-test-email.json", draft)
            report["draft_id"] = draft["id"]
            report["send_authorization"] = "User requested one actual test including email to supplier."
            report["no_job_before_email_approval"] = not run_once(app.state.factory, settings)
            save(report_path, report)
            api("POST", f"/drafts/{draft['id']}/approve", json={"version": draft["version"]})
            run_once(app.state.factory, settings)
        drafts = api("GET", "/drafts")
        draft = next(d for d in drafts if d["id"] == report.get("draft_id"))
        report["email"] = {k: draft[k] for k in ("id", "status", "provider_id", "recipient", "subject")}
        save(report_path, report)
        if draft["status"] != "sent":
            raise SystemExit("Test email is not confirmed sent; inspect jobs. No automatic resend attempted.")
        with Gmail(settings) as gmail:
            gmail.authorize()
            sent = gmail.get(f"/messages/{draft['provider_id']}", {"format": "minimal"})
        report["gmail_sent_label_verified"] = "SENT" in sent.get("labelIds", [])
        print("Live Gmail request:", draft["status"], draft["provider_id"], flush=True)

        if args.sync_replies:
            report["real_reply_sync"] = api("POST", "/automation/gmail/sync", headers=automation)
        elif "synthetic_message_id" not in report:
            body = (
                f"TEST ONLY. I am {PERSON} of {SUPPLIER}; contact {CONTACT}.\n"
                f"Supplier {SUPPLIER_ID}, article {ARTICLE}.\n"
                f"{ROW}=2028-12-31\nThe certificate expires on 31 December 2028.\n"
                f"Please respond to {settings.gmail_supplier}.\n"
            )
            (output / "supplier-reply-template.txt").write_text(
                f"Reply from {settings.gmail_supplier} to {settings.gmail_mailbox}\n"
                f"Subject: Re: {draft['subject']}\n\n{body}"
            )
            pdf = io.BytesIO()
            document = canvas.Canvas(pdf)
            document.drawString(72, 720, f"TEST ONLY: {SUPPLIER}")
            document.drawString(72, 700, f"Contact: {PERSON}, {CONTACT}")
            document.drawString(72, 680, "The certificate expires on 31 December 2028.")
            document.save()
            data = {"external_id": "synthetic-live-check:" + report["case_id"],
                    "sender": settings.gmail_supplier, "body": body}
            message = api("POST", f"/cases/{report['case_id']}/messages", headers=automation,
                          data=data, files={"attachments": (
                              "private-supplier-certificate.pdf", pdf.getvalue(), "application/pdf")})
            report["synthetic_message_id"] = message["id"]
            duplicate = api("POST", f"/cases/{report['case_id']}/messages",
                            headers=automation, data=data)
            report["duplicate_reply_deduplicated"] = duplicate["duplicate"]
            save(report_path, report)

        if not args.sync_replies and not report.get("extraction_passed"):
            with patch("httpx.request", observe_anymize), patch("httpx.post", observe_gemini):
                while run_once(app.state.factory, settings):
                    pass
            report[run_label + "-anymize_calls"] = anymize_calls
            report[run_label + "-gemini_calls"] = gemini_calls
        report["jobs"] = api("GET", "/jobs")
        proposals = api("GET", "/proposals")
        report["proposals"] = proposals
        export = client.get("/exports/submissions.csv", headers=review)
        export.raise_for_status()
        report["accepted_value_unchanged"] = all(
            row["Value submitted"] == "" for row in csv.DictReader(io.StringIO(export.text))
        )
        report["extraction_passed"] = any(
            p["field_id"] == ROW and p["value"] == "2028-12-31"
            and p["status"] == "pending" and not p["validation_errors"] for p in proposals
        )
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(report_path, report)
        print("Fictional reply extraction:", report["extraction_passed"], flush=True)
        if args.sync_replies:
            print("Real reply sync:", report["real_reply_sync"], flush=True)
            print("Real replies are queued only; hosted anonymization privacy gap remains.", flush=True)
        print("Report:", report_path, flush=True)
        if any(j["status"] == "failed" for j in report["jobs"]) or not report["extraction_passed"]:
            raise SystemExit(1)
    engine.dispose()


if __name__ == "__main__":
    main()
