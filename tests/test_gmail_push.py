import base64
import json

import httpx
import pytest

from nova import gmail_push
from tests.conftest import AUTOMATION


def configure(env):
    client, _, settings = env
    settings.gmail_push_topic = "projects/demo/topics/inbox"
    settings.gmail_push_audience = "https://nova.example/mail/gmail/push"
    settings.gmail_push_service_account = "push@demo.iam.gserviceaccount.com"
    settings.gmail_push_subscription = "projects/demo/subscriptions/inbox"
    settings.gmail_push_webhook = "https://n8n.example/webhook/nova-gmail-push"
    body = {
        "subscription": settings.gmail_push_subscription,
        "message": {
            "data": base64.urlsafe_b64encode(
                json.dumps({"emailAddress": settings.gmail_mailbox, "historyId": "123"}).encode()
            ).decode()
        },
    }
    return client, settings, body


def test_push_requires_signed_expected_identity(env, monkeypatch):
    client, settings, body = configure(env)
    assert client.post("/mail/gmail/push", json=body).status_code == 401
    assert client.post("/mail/gmail/push", json=body, headers=AUTOMATION).status_code == 401

    def claims(*args):
        assert args[2] == settings.gmail_push_audience
        return {"email": "wrong@example.com", "email_verified": True}

    monkeypatch.setattr(gmail_push.id_token, "verify_oauth2_token", claims)
    assert (
        client.post("/mail/gmail/push", json=body, headers={"Authorization": "Bearer signed"}).status_code
        == 401
    )


@pytest.mark.parametrize("failure", [False, True])
def test_push_sends_only_signal_and_retries_failed_sync(env, monkeypatch, failure):
    client, settings, body = configure(env)
    monkeypatch.setattr(gmail_push, "verify_push_token", lambda *args: None)
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs)
        assert url == settings.gmail_push_webhook
        assert kwargs["json"] == {"event": "gmail_inbox_changed"}
        return httpx.Response(
            503 if failure else 200, json={"status": "synced"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(gmail_push.httpx, "post", post)
    result = client.post("/mail/gmail/push", json=body, headers={"Authorization": "Bearer signed"})
    assert result.status_code == (503 if failure else 204)
    assert len(calls) == 1
    body["subscription"] = "wrong"
    assert (
        client.post("/mail/gmail/push", json=body, headers={"Authorization": "Bearer signed"}).status_code
        == 400
    )
    assert len(calls) == 1


def test_watch_requires_operator_and_reports_expiry(env, monkeypatch):
    client, settings, _ = configure(env)
    assert client.post("/automation/gmail/watch").status_code == 401
    calls = []

    def authorize(gmail):
        gmail.token = "oauth-test"
        gmail.http.close()

        def handle(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"historyId": "123", "expiration": "9999999999"})

        gmail.http = httpx.Client(transport=httpx.MockTransport(handle))

    monkeypatch.setattr(gmail_push.Gmail, "authorize", authorize)
    response = client.post("/automation/gmail/watch", headers=AUTOMATION)
    assert response.json() == {"expiration": "9999999999"}
    assert calls == [
        {"topicName": settings.gmail_push_topic, "labelIds": ["INBOX"], "labelFilterBehavior": "INCLUDE"}
    ]
