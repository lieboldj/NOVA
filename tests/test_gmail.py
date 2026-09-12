import base64
import json
from email import policy
from email.parser import BytesParser

import httpx
import pytest
from sqlalchemy import select

from nova.gmail import Gmail, GmailNotSent
from nova.models import Document, Draft, Job, Message, SupplierField
from nova.worker import run_once
from tests.conftest import AUTOMATION, REVIEW, approve_email, request_draft, seed


def encoded(text):
    return base64.urlsafe_b64encode(text if isinstance(text, bytes) else text.encode()).decode().rstrip("=")


def setup(env, monkeypatch, *, fail_send=None, wrong_account=False):
    client, factory, settings = env
    settings.mail_mode = "gmail"
    from pydantic import SecretStr

    settings.gmail_client_id = SecretStr("test-client")
    settings.gmail_client_secret = SecretStr("test-secret")
    settings.gmail_refresh_token = SecretStr("test-refresh")
    case_id = seed(client)
    assert (
        client.post(
            f"/cases/{case_id}/contact/approve",
            headers=REVIEW,
            json={"revision": 1, "recipient": settings.gmail_supplier},
        ).status_code
        == 200
    )
    calls, payloads = [], {}

    def handle(request):
        calls.append(request)
        path = request.url.path
        if path == "/token":
            return httpx.Response(200, json={"access_token": "test-access"})
        if path.endswith("/profile"):
            return httpx.Response(
                200, json={"emailAddress": "wrong@example.com" if wrong_account else settings.gmail_mailbox}
            )
        if path.endswith("/messages/send"):
            if fail_send == "timeout":
                raise httpx.ReadTimeout("unsafe provider details", request=request)
            return httpx.Response(fail_send or 200, json={"id": "sent123"})
        if path.endswith("/messages"):
            return httpx.Response(
                200, json={"messages": [{"id": key} for key in payloads], "nextPageToken": "page2"}
            )
        key = path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=payloads[key])

    original = Gmail.__init__

    def init(self, settings):
        original(self, settings)
        self.http.close()
        self.http = httpx.Client(transport=httpx.MockTransport(handle))

    monkeypatch.setattr(Gmail, "__init__", init)
    return case_id, calls, payloads


def test_only_frontend_approved_version_is_sent(env, monkeypatch):
    client, factory, settings = env
    case_id, calls, _ = setup(env, monkeypatch)
    draft = request_draft(client, case_id)
    assert not run_once(factory, settings)
    assert not calls
    assert (
        client.post(
            f"/drafts/{draft['id']}/approve", headers=AUTOMATION, json={"version": draft["version"]}
        ).status_code
        == 403
    )
    approve_email(client, draft)
    run_once(factory, settings)
    sent = [call for call in calls if call.url.path.endswith("/send")]
    assert len(sent) == 1
    raw = base64.urlsafe_b64decode(json.loads(sent[0].content)["raw"])
    mail = BytesParser(policy=policy.default).parsebytes(raw)
    assert mail["From"] == settings.gmail_mailbox
    assert mail["To"] == settings.gmail_supplier
    assert mail["Subject"] == draft["subject"]
    assert mail.get_content().rstrip() == draft["body"].rstrip()
    with factory() as db:
        assert db.get(Draft, draft["id"]).status == "sent"
    assert not run_once(factory, settings)


@pytest.mark.parametrize("failure,expected,retry", [(403, "approved", 200), ("timeout", "uncertain", 409)])
def test_rejected_vs_ambiguous_send(env, monkeypatch, failure, expected, retry):
    client, factory, settings = env
    case_id, _, _ = setup(env, monkeypatch, fail_send=failure)
    draft = request_draft(client, case_id)
    approve_email(client, draft)
    run_once(factory, settings)
    with factory() as db:
        assert db.get(Draft, draft["id"]).status == expected
        job = db.scalar(select(Job).where(Job.kind == "send"))
        assert "unsafe" not in job.error
    assert client.post(f"/jobs/{job.id}/retry", headers=REVIEW).status_code == retry


def test_wrong_oauth_account_never_sends(env, monkeypatch):
    client, factory, settings = env
    case_id, calls, _ = setup(env, monkeypatch, wrong_account=True)
    draft = request_draft(client, case_id)
    approve_email(client, draft)
    run_once(factory, settings)
    assert not any(call.url.path.endswith("/send") for call in calls)
    assert client.get("/mail/gmail/status", headers=REVIEW).json()["connected"] is False


def test_missing_credentials_and_recipient_guard(env):
    _, _, settings = env
    settings.mail_mode = "gmail"
    from pydantic import SecretStr

    settings.gmail_refresh_token = SecretStr("")
    with Gmail(settings) as gmail:
        with pytest.raises(GmailNotSent):
            gmail.authorize()
        with pytest.raises(GmailNotSent):
            gmail.send(Draft(recipient="unexpected@example.com"))


def test_inbox_sync_pdf_and_deduplication_preserves_values(env, monkeypatch):
    client, factory, settings = env
    case_id, calls, payloads = setup(env, monkeypatch)
    draft = request_draft(client, case_id)
    approve_email(client, draft)
    run_once(factory, settings)
    payloads["reply123"] = {
        "payload": {
            "headers": [
                {"name": "From", "value": settings.gmail_supplier},
                {"name": "Subject", "value": "Re: " + draft["subject"]},
            ],
            "mimeType": "multipart/mixed",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": encoded("F1=Supplier value")}},
                {
                    "mimeType": "application/pdf",
                    "filename": "certificate.pdf",
                    "body": {"attachmentId": "attachment123", "size": 20},
                },
            ],
        }
    }
    # Attachment endpoint response is separate from the message payload.
    payloads["attachment123"] = {"data": encoded(b"%PDF-1.4\nfixture")}
    response = client.post("/automation/gmail/sync?page_token=previous", headers=AUTOMATION)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["next_page_token"] == "page2"
    assert result["results"][0]["duplicate"] is False
    message_id = result["results"][0]["id"]
    again = client.post("/automation/gmail/sync", headers=AUTOMATION).json()
    assert again["results"][0]["duplicate"] is True
    with factory() as db:
        assert len(db.scalars(select(Message)).all()) == 1
        document = db.scalar(select(Document).where(Document.message_id == message_id))
        assert (settings.storage_path / document.storage_key).read_bytes().startswith(b"%PDF-")
        assert db.get(SupplierField, "F1").data["Value submitted"] == ""
        assert db.scalar(select(Job).where(Job.kind == "evaluate")).status == "queued"
    assert any(call.url.params.get("pageToken") == "previous" for call in calls)
    assert not any(call.url.path.endswith(("/modify", "/trash")) for call in calls)
    assert client.get("/mail/gmail/messages/reply123", headers=AUTOMATION).status_code == 403
    assert client.get("/mail/gmail/messages/reply123", headers=REVIEW).json()["body"] == "F1=Supplier value"


def test_unroutable_and_unsupported_mail_requires_review(env, monkeypatch):
    client, factory, settings = env
    case_id, _, payloads = setup(env, monkeypatch)
    draft = request_draft(client, case_id)
    approve_email(client, draft)
    run_once(factory, settings)
    for key, subject, parts in [
        ("unrouted", "Hello", [{"mimeType": "text/plain", "body": {"data": encoded("Hello")}}]),
        (
            "unsupported",
            draft["subject"],
            [{"mimeType": "application/zip", "filename": "data.zip", "body": {"data": encoded(b"PK000")}}],
        ),
    ]:
        payloads[key] = {
            "payload": {
                "headers": [
                    {"name": "From", "value": settings.gmail_supplier},
                    {"name": "Subject", "value": subject},
                ],
                "parts": parts,
            }
        }
    response = client.post("/automation/gmail/sync", headers=AUTOMATION)
    assert all(r["status"] == "manual_review" for r in response.json()["results"])
    with factory() as db:
        assert not db.scalars(select(Message)).all()


def test_html_only_reply(env, monkeypatch):
    client, _, settings = env
    _, _, payloads = setup(env, monkeypatch)
    payloads["html123"] = {
        "payload": {
            "headers": [
                {"name": "From", "value": settings.gmail_supplier},
                {"name": "Subject", "value": "Hello"},
            ],
            "mimeType": "text/html",
            "body": {"data": encoded("<p>Value &amp; evidence</p><script>hidden</script>")},
        }
    }
    response = client.get("/mail/gmail/messages/html123", headers=REVIEW)
    assert response.json()["body"].strip() == "Value & evidence"
