"""Authenticated Gmail notification relay. Only a wake-up signal reaches n8n."""

import base64
import json

import httpx
from fastapi import HTTPException, Request, Response
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from nova.gmail import ROOT, Gmail, GmailUnavailable


def verify_push_token(token, settings):
    claims = id_token.verify_oauth2_token(token, GoogleRequest(), settings.gmail_push_audience)
    if claims.get("email") != settings.gmail_push_service_account or claims.get("email_verified") is not True:
        raise ValueError("Unexpected push identity")


def install_push_routes(app, settings, Operator):
    @app.post("/automation/gmail/watch", tags=["Gmail"])
    def renew_watch(actor: Operator):
        if not settings.gmail_push_topic:
            raise HTTPException(503, "Gmail push is not configured")
        try:
            with Gmail(settings) as gmail:
                gmail.authorize()
                result = gmail.http.post(
                    ROOT + "/watch",
                    headers={"Authorization": "Bearer " + gmail.token},
                    json={
                        "topicName": settings.gmail_push_topic,
                        "labelIds": ["INBOX"],
                        "labelFilterBehavior": "INCLUDE",
                    },
                )
                result.raise_for_status()
                return {"expiration": result.json()["expiration"]}
        except (GmailUnavailable, httpx.HTTPError, KeyError, ValueError):
            raise HTTPException(503, "Gmail watch renewal failed") from None

    @app.post("/mail/gmail/push", tags=["Gmail"], status_code=204)
    def push(request: Request, body: dict):
        if not all(
            (
                settings.gmail_push_audience,
                settings.gmail_push_service_account,
                settings.gmail_push_subscription,
                settings.gmail_push_webhook,
            )
        ):
            raise HTTPException(503, "Gmail push is not configured")
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Push authentication required")
        try:
            verify_push_token(authorization[7:], settings)
        except Exception:
            raise HTTPException(401, "Invalid push identity") from None
        try:
            if body["subscription"] != settings.gmail_push_subscription:
                raise ValueError()
            encoded = body["message"]["data"]
            if not isinstance(encoded, str) or len(encoded) > 8192:
                raise ValueError()
            notification = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if notification["emailAddress"].casefold() != settings.gmail_mailbox.casefold():
                raise ValueError()
            if not str(notification["historyId"]).isdigit():
                raise ValueError()
        except (KeyError, ValueError, TypeError, AttributeError):
            raise HTTPException(400, "Invalid Gmail notification") from None
        try:
            # Wait for the full n8n sync before acknowledging: Pub/Sub retries failures.
            # Do not pass email addresses, notification contents, or OAuth tokens to n8n.
            result = httpx.post(
                settings.gmail_push_webhook,
                headers={"Authorization": "Bearer " + settings.nova_automation_token.get_secret_value()},
                json={"event": "gmail_inbox_changed"},
                timeout=180,
            )
            result.raise_for_status()
            if result.json().get("status") != "synced":
                raise ValueError()
        except (httpx.HTTPError, ValueError, AttributeError):
            raise HTTPException(503, "Gmail sync unavailable; retry notification") from None
        return Response(status_code=204)
