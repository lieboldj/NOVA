import hashlib
from pathlib import Path

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from nova.models import Case, Document, Draft, Message, now, uid
from nova.workflow import audit, enqueue, fail, invalidate_drafts, locked


def ingest_message(db, settings, case_id, external_id, sender, body, attachments, actor):
    if len(external_id) > 500 or not external_id or len(body) > 100000 or len(attachments) > 10:
        fail("Message exceeds input limits", 422)
    case = locked(db, Case, case_id)
    existing = db.scalar(select(Message).where(Message.external_id == external_id))
    if existing:
        if existing.case_id != case.id:
            fail("Message already belongs to another case")
        return {"id": existing.id, "status": existing.status, "duplicate": True}
    try:
        sender = str(TypeAdapter(EmailStr).validate_python(sender))
    except ValidationError:
        fail("Invalid sender email", 422)
    if sender.casefold() != case.recipient.casefold():
        fail("Sender does not match approved supplier contact; manual routing required")
    sent = db.scalar(
        select(Draft)
        .where(Draft.case_id == case.id, Draft.status.in_(["sent", "simulated"]))
        .order_by(Draft.created_at.desc())
        .limit(1)
    )
    if not sent:
        fail("Send an approved request before ingesting a reply")
    if not body.strip() and not attachments:
        fail("Reply requires text or an attachment", 422)
    uploads = []
    total = len(body.encode())
    for filename, data in attachments:
        total += len(data)
        if total > settings.upload_limit_bytes:
            fail("Message exceeds upload limit", 413)
        if data.startswith(b"%PDF-"):
            kind = "application/pdf"
        elif (filename or "").lower().endswith(".txt"):
            try:
                data.decode("utf-8")
            except UnicodeError:
                fail("Text attachment must be UTF-8", 422)
            kind = "text/plain"
        else:
            fail("Supported attachments: PDF and UTF-8 TXT", 422)
        uploads.append((filename or "attachment", kind, data))
    message = Message(
        case_id=case.id,
        external_id=external_id,
        sender=sender,
        body=body,
        requested_fields=sent.requested_fields,
    )
    db.add(message)
    db.flush()
    for name, kind, data in uploads:
        key = uid()
        (settings.storage_path / key).write_bytes(data)
        db.add(
            Document(
                message_id=message.id,
                filename=Path(name).name,
                content_type=kind,
                storage_key=key,
                sha256=hashlib.sha256(data).hexdigest(),
            )
        )
    invalidate_drafts(db, case)
    case.last_reply_at, case.next_action_at, case.status = now(), None, "processing_reply"
    case.reminders_sent = 0
    enqueue(db, "evaluate", message.id, "evaluate:" + message.id)
    audit(db, actor, "reply.received", message.id, case_id=case.id)
    return {"id": message.id, "status": message.status, "duplicate": False}
