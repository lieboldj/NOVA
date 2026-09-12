"""Trusted Gmail transport. No mailbox credentials or raw inbox are given to the model."""

import base64
import re
from email.message import EmailMessage
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import HTTPException, Query
from sqlalchemy import select

from nova.inbox import ingest_message
from nova.models import Message

ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailUnavailable(Exception):
    """Safe, content-free errors, never provider responses or credentials."""


class GmailNotSent(GmailUnavailable):
    """A failure before transmission, or an explicit Gmail rejection."""


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag in ("br", "p", "div", "li", "tr"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


class Gmail:
    @staticmethod
    def configured(settings):
        return all(
            x.get_secret_value()
            for x in (settings.gmail_client_id, settings.gmail_client_secret, settings.gmail_refresh_token)
        )

    def __init__(self, settings):
        self.settings = settings
        self.http = httpx.Client(timeout=30)
        self.token = None
        self.verified = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.http.close()

    def authorize(self):
        if self.verified:
            return
        if not self.configured(self.settings):
            raise GmailNotSent("Gmail OAuth credentials are missing.")
        try:
            response = self.http.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.settings.gmail_client_id.get_secret_value(),
                    "client_secret": self.settings.gmail_client_secret.get_secret_value(),
                    "refresh_token": self.settings.gmail_refresh_token.get_secret_value(),
                },
            )
            response.raise_for_status()
            self.token = response.json()["access_token"]
            profile = self.get("/profile")
            if profile["emailAddress"].casefold() != self.settings.gmail_mailbox.casefold():
                raise GmailNotSent("OAuth account does not match the configured internal mailbox.")
            self.verified = True
        except GmailNotSent:
            raise
        except Exception:
            raise GmailNotSent("Gmail authorization failed; check credentials and account access.") from None

    def get(self, path, params=None):
        try:
            response = self.http.get(
                ROOT + path, params=params, headers={"Authorization": f"Bearer {self.token}"}
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            raise GmailUnavailable("Gmail read failed; check account access and retry.") from None

    def send(self, draft):
        # The worker has already durably verified the exact human-approved version/digest.
        if draft.recipient.casefold() != self.settings.gmail_supplier.casefold():
            raise GmailNotSent("Recipient is outside the configured test supplier mailbox.")
        try:
            message = EmailMessage()
            message["From"] = self.settings.gmail_mailbox
            message["To"] = draft.recipient
            message["Subject"] = draft.subject
            message["X-NOVA-Message-Type"] = "request"
            message["Message-ID"] = (
                f"<nova-{draft.id}-v{draft.version}@{self.settings.gmail_mailbox.split('@')[1]}>"
            )
            message.set_content(draft.body)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        except Exception:
            raise GmailNotSent("Invalid email headers or mailbox configuration.") from None
        self.authorize()
        # Never retry this POST: a connection failure can occur after Gmail accepted the mail.
        response = self.http.post(
            ROOT + "/messages/send", json={"raw": raw}, headers={"Authorization": f"Bearer {self.token}"}
        )
        if 400 <= response.status_code < 500 and response.status_code != 408:
            raise GmailNotSent("Gmail rejected the email; check access and configuration.")
        response.raise_for_status()
        return response.json()["id"]

    def list_inbox(self, page_token=None):
        self.authorize()
        params = {"q": f"in:inbox from:{self.settings.gmail_supplier}", "maxResults": 20}
        if page_token:
            params["pageToken"] = page_token
        return self.get("/messages", params)

    def message(self, message_id):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", message_id):
            raise GmailUnavailable("Invalid Gmail message ID.")
        self.authorize()
        data = self.get(f"/messages/{message_id}", {"format": "full"})
        payload = data.get("payload", {})
        headers = {}
        for header in payload.get("headers", []):
            headers.setdefault(header["name"].lower(), []).append(header["value"])
        if len(headers.get("from", [])) != 1 or len(headers.get("subject", [])) != 1:
            raise GmailUnavailable("Ambiguous message headers; manual review required.")
        sender = parseaddr(headers["from"][0])[1]
        if sender.casefold() != self.settings.gmail_supplier.casefold():
            raise GmailUnavailable("Message sender is outside the test supplier mailbox.")
        plain, html, attachments = [], [], []
        total = 0

        def walk(part, depth=0):
            nonlocal total
            if depth > 30:
                raise GmailUnavailable("Message nesting exceeds processing limit.")
            body = part.get("body", {})
            if body.get("size", 0) + total > self.settings.upload_limit_bytes:
                raise GmailUnavailable("Message exceeds upload limit; manual review required.")
            encoded = body.get("data", "")
            if body.get("attachmentId"):
                attachment_id = body["attachmentId"]
                if not re.fullmatch(r"[a-zA-Z0-9_-]+", attachment_id):
                    raise GmailUnavailable("Invalid attachment ID.")
                encoded = self.get(f"/messages/{message_id}/attachments/{attachment_id}").get("data", "")
            try:
                content = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
            except Exception:
                raise GmailUnavailable("Invalid message encoding; manual review required.") from None
            total += len(content)
            if total > self.settings.upload_limit_bytes:
                raise GmailUnavailable("Message exceeds upload limit; manual review required.")
            filename = part.get("filename", "")
            mime = part.get("mimeType", "")
            if filename or (content and mime not in ("text/plain", "text/html")):
                attachments.append((filename or "attachment", content))
            elif content:
                charset = "utf-8"
                for header in part.get("headers", []):
                    if header["name"].lower() == "content-type":
                        match = re.search(r'charset=["\']?([^;"\'\s]+)', header["value"], re.I)
                        if match:
                            charset = match[1]
                try:
                    text = content.decode(charset)
                except (UnicodeError, LookupError):
                    raise GmailUnavailable("Unsupported text encoding; manual review required.") from None
                (plain if mime == "text/plain" else html).append(text)
            for child in part.get("parts", []):
                walk(child, depth + 1)

        walk(payload)
        if plain:
            text = "\n".join(plain)
        else:
            parser = PlainHTML()
            parser.feed("\n".join(html))
            text = "".join(parser.text)
        return {
            "gmail_id": message_id,
            "sender": sender,
            "subject": headers["subject"][0],
            "body": text,
            "attachments": attachments,
            "is_nova_request": (
                "request" in headers.get("x-nova-message-type", [])
                or any(
                    re.fullmatch(r"<nova-[0-9a-f-]{36}-v\d+@[^>]+>", value)
                    for value in headers.get("message-id", [])
                )
            ),
        }


def install_gmail_routes(app, settings, Reviewer, Operator):
    @app.get("/mail/gmail/status", tags=["Gmail"])
    def status(actor: Reviewer):
        result = {
            "mailbox": settings.gmail_mailbox,
            "supplier": settings.gmail_supplier,
            "configured": Gmail.configured(settings),
            "connected": False,
        }
        try:
            with Gmail(settings) as gmail:
                gmail.authorize()
            result["connected"] = True
        except GmailUnavailable as error:
            result["reason"] = str(error)
        return result

    @app.get("/mail/gmail/inbox", tags=["Gmail"])
    def inbox(actor: Reviewer, page_token: Annotated[str | None, Query(max_length=2000)] = None):
        try:
            with Gmail(settings) as gmail:
                return gmail.list_inbox(page_token)
        except GmailUnavailable as error:
            raise HTTPException(503, str(error)) from None

    @app.get("/mail/gmail/messages/{message_id}", tags=["Gmail"])
    def read(message_id: str, actor: Reviewer):
        try:
            with Gmail(settings) as gmail:
                message = gmail.message(message_id)
            message["attachments"] = [
                {"filename": name, "size": len(data)} for name, data in message["attachments"]
            ]
            return message
        except GmailUnavailable as error:
            raise HTTPException(503, str(error)) from None

    @app.post("/automation/gmail/sync", tags=["Gmail"])
    def sync(actor: Operator, page_token: Annotated[str | None, Query(max_length=2000)] = None):
        results = []
        try:
            with Gmail(settings) as gmail:
                page = gmail.list_inbox(page_token)
                for item in page.get("messages", []):
                    external_id = f"gmail:{settings.gmail_mailbox.casefold()}:{item['id']}"
                    with app.state.factory() as db:
                        existing = db.scalar(select(Message).where(Message.external_id == external_id))
                        if existing:
                            results.append({"gmail_id": item["id"], "id": existing.id, "duplicate": True})
                            continue
                    try:
                        message = gmail.message(item["id"])
                        # A single mailbox can play both sides of a test. Never ingest our
                        # own request as a supplier answer, even before send persistence completes.
                        if message["is_nova_request"]:
                            results.append({"gmail_id": item["id"], "status": "outgoing_request"})
                            continue
                        matches = set(re.findall(r"\[NOVA:([0-9a-fA-F-]{36})\]", message["subject"]))
                        if len(matches) != 1:
                            raise GmailUnavailable(
                                "Missing or ambiguous NOVA case reference; manual routing required."
                            )
                        try:
                            case_id = str(UUID(matches.pop()))
                        except ValueError:
                            raise GmailUnavailable("Invalid NOVA case reference.") from None
                        with app.state.factory.begin() as db:
                            result = ingest_message(
                                db,
                                settings,
                                case_id,
                                external_id,
                                message["sender"],
                                message["body"],
                                message["attachments"],
                                actor,
                            )
                        results.append({"gmail_id": item["id"], **result})
                    except (GmailUnavailable, HTTPException) as error:
                        reason = error.detail if isinstance(error, HTTPException) else str(error)
                        results.append({"gmail_id": item["id"], "status": "manual_review", "reason": reason})
            return {"results": results, "next_page_token": page.get("nextPageToken")}
        except GmailUnavailable as error:
            raise HTTPException(503, str(error)) from None
