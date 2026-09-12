import io
import json
import re
import time
from datetime import timedelta

from pypdf import PdfReader
from sqlalchemy import select

from nova.config import get_settings
from nova.db import make_engine, sessions
from nova.gmail import GmailNotSent
from nova.models import Case, Document, Draft, Job, Message, Proposal, SupplierField, now, uid
from nova.providers import ProviderUnavailable, known_redaction, known_restore, providers, send_email
from nova.workflow import audit, draft_digest, locked, locked_child, validate_value


def claim_job(factory):
    with factory.begin() as db:
        # A send interrupted after transmission has an ambiguous outcome: never blindly retry it.
        expired = db.scalars(
            select(Job)
            .where(Job.status == "running", Job.lease_until < now())
            .with_for_update(skip_locked=True)
        ).all()
        for job in expired:
            if job.kind == "send":
                job.status, job.error = "failed", "Sending outcome unknown; manual reconciliation required."
                draft = db.get(Draft, job.target_id)
                if draft and draft.status == "sending":
                    draft.status = "uncertain"
            else:
                job.status = "queued"
        job = db.scalar(
            select(Job)
            .where(Job.status == "queued", Job.available_at <= now())
            .order_by(Job.available_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return None
        job.status = "running"
        job.attempts += 1
        job.claim_token = uid()
        job.lease_until = now() + timedelta(minutes=15)
        return job.id, job.claim_token, job.kind, job.target_id


def own_job(db, job_id, token):
    job = locked(db, Job, job_id)
    if job.status != "running" or job.claim_token != token:
        raise ProviderUnavailable("Job lease was replaced; stale result discarded.")
    return job


def send_job(factory, settings, job_id, token, target_id):
    with factory.begin() as db:
        job = own_job(db, job_id, token)
        draft = locked_child(db, Draft, target_id)
        case = db.get(Case, draft.case_id)
        if job.dedupe_key != f"send:{draft.id}:{draft.version}":
            # An old delivery job must not invalidate a newer, separately approved version.
            job.status = "cancelled"
            return
        if (
            draft.status != "approved"
            or not draft.approved_by
            or draft.approved_digest != draft_digest(draft)
            or draft.case_revision != case.revision
        ):
            if draft.status == "approved":
                draft.status = "superseded"
            job.status = "cancelled"
            return
        draft.status = "sending"
    # Transmission is outside the DB transaction. "sending" is durable before the side effect.
    try:
        result = send_email(settings, draft)
    except GmailNotSent:
        with factory.begin() as db:
            job = own_job(db, job_id, token)
            locked(db, Case, draft.case_id)
            current = db.get(Draft, target_id)
            current.status = "approved"
            job.status, job.error = "failed", "Gmail did not send; check configuration and retry."
            audit(db, "worker", "email.send_blocked", target_id)
        return
    except Exception:
        with factory.begin() as db:
            job = own_job(db, job_id, token)
            locked(db, Case, draft.case_id)
            current = db.get(Draft, target_id)
            current.status = "uncertain"
            job.status, job.error = "failed", "Sending outcome unknown; manual reconciliation required."
            audit(db, "worker", "email.send_uncertain", target_id)
        return
    with factory.begin() as db:
        job = own_job(db, job_id, token)
        case = locked(db, Case, draft.case_id)
        current = db.get(Draft, target_id)
        current.provider_id = result
        current.status = "simulated" if settings.mail_mode == "simulation" else "sent"
        case.last_sent_at = now()
        if case.revision == draft.case_revision:
            case.next_action_at = now() + timedelta(days=settings.response_days)
            case.status = "awaiting_reply"
        if draft.kind == "reminder":
            case.reminders_sent += 1
        job.status = "done"
        audit(db, "worker", "email." + current.status, current.id, provider_id=result)


def raw_sources(db, settings, message, anonymizer):
    sources = [{"source_id": "email", "text": message.body, "page": None, "document_id": None}]
    for doc in db.scalars(select(Document).where(Document.message_id == message.id)):
        content = (settings.storage_path / doc.storage_key).read_bytes()
        if doc.content_type == "text/plain":
            sources.append(
                {"source_id": doc.id, "text": content.decode("utf-8"), "page": None, "document_id": doc.id}
            )
        else:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > 100:
                raise ProviderUnavailable("Encrypted PDFs or PDFs over 100 pages need manual review.")
            pages = [(page.extract_text() or "") for page in reader.pages]
            # OCR pages that do not expose text, including scanned pages in mixed PDFs.
            for i, page_text in enumerate(pages, 1):
                if not page_text.strip():
                    from pypdf import PdfWriter

                    writer = PdfWriter()
                    writer.add_page(reader.pages[i - 1])
                    stream = io.BytesIO()
                    writer.write(stream)
                    page_text = anonymizer.document(stream.getvalue())
                sources.append(
                    {"source_id": f"{doc.id}:p{i}", "text": page_text, "page": i, "document_id": doc.id}
                )
    if sum(len(s["text"]) for s in sources) > 300000:
        raise ProviderUnavailable("Evidence exceeds processing limit; split or review manually.")
    return sources


def evaluate_job(factory, settings, job_id, token, target_id):
    anonymizer, evaluator = providers(settings)
    with factory.begin() as db:
        own_job(db, job_id, token)
        message = db.get(Message, target_id)
        case = locked(db, Case, message.case_id)
        message.status = "processing"
        fields = db.scalars(
            # Suppliers can confirm accepted values or volunteer other case fields.
            # The full original reply remains reviewable even without an extracted candidate.
            select(SupplierField).where(SupplierField.case_id == case.id).order_by(SupplierField.id)
        ).all()
        documents = db.scalars(select(Document).where(Document.message_id == message.id)).all()
    # Read evidence without holding a case lock during external requests.
    with factory() as db:
        sources = raw_sources(db, settings, message, anonymizer)
    aliases = {f.id: f"FIELD_{i:04d}" for i, f in enumerate(fields, 1)}
    field_payload = [
        {
            "field_id": aliases[f.id],
            "label": f.data["Field (label)"],
            "section": f.data["Section"],
            "field_type": f.data["Field Type"],
            "current_value": f.data["Value submitted"],
            "rules": f.rules,
        }
        for f in fields
    ]
    bundle = {
        "fields": field_payload,
        "sources": [{"source_id": s["source_id"], "text": s["text"]} for s in sources],
    }

    # Identifiers are handled locally first; all free text then crosses the Anymize boundary.
    def redact(value):
        if isinstance(value, str):
            value = known_redaction(value, case)
            for field_id, alias in sorted(aliases.items(), key=lambda item: -len(item[0])):
                value = re.sub(r"(?<![\w])" + re.escape(field_id) + r"(?![\w])", lambda _: alias, value)
            return value
        if isinstance(value, list):
            return [redact(item) for item in value]
        if isinstance(value, dict):
            return {key: redact(item) for key, item in value.items()}
        return value

    sanitized_text = anonymizer.text(json.dumps(redact(bundle), ensure_ascii=False))
    try:
        sanitized = json.loads(sanitized_text)
        if set(sanitized) != {"fields", "sources"}:
            raise ValueError()
        if {f["field_id"] for f in sanitized["fields"]} != set(aliases.values()):
            raise ValueError()
        if {s["source_id"] for s in sanitized["sources"]} != {s["source_id"] for s in sources}:
            raise ValueError()
        if not all(isinstance(s["text"], str) for s in sanitized["sources"]):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ProviderUnavailable(
            "Sanitization changed the evidence structure; manual review required."
        ) from None
    # The evaluator receives only the explicitly selected sanitized fields, never provider metadata.
    evaluation = evaluator.evaluate(sanitized["fields"], sanitized["sources"])
    source_by_id = {s["source_id"]: s for s in sources}
    safe_by_id = {s["source_id"]: s for s in sanitized["sources"]}
    field_by_id = {aliases[f.id]: f for f in fields}
    proposed = []
    seen = set()
    for candidate in evaluation.candidates:
        if candidate.field_id not in field_by_id or candidate.field_id in seen:
            raise ProviderUnavailable("Evaluation contains duplicate or unrequested fields.")
        seen.add(candidate.field_id)
        src = source_by_id.get(candidate.evidence.source_id)
        safe = safe_by_id.get(candidate.evidence.source_id)
        if not src or not safe or candidate.evidence.quote not in safe["text"]:
            raise ProviderUnavailable("Evaluation evidence does not match the supplied source.")
        field = field_by_id[candidate.field_id]
        value = known_restore(anonymizer.restore(candidate.value), case)
        errors = validate_value(field, value)
        if "upload" in field.data["Field Type"].lower():
            if not src["document_id"]:
                errors.append("A file field requires an attached evidence document.")
            else:
                value = "document://" + src["document_id"]
        quote = known_restore(anonymizer.restore(candidate.evidence.quote), case)
        for original_id, alias in aliases.items():
            quote = quote.replace(alias, original_id)
        proposed.append(
            Proposal(
                case_id=case.id,
                message_id=message.id,
                field_id=field.id,
                old_value=field.data["Value submitted"],
                field_revision=field.revision,
                value=value,
                rationale=known_restore(anonymizer.restore(candidate.rationale), case),
                evidence={
                    "source_id": src["source_id"],
                    "document_id": src["document_id"],
                    "page": src["page"],
                    "quote": quote,
                },
                validation_errors=errors,
            )
        )
    with factory.begin() as db:
        job = own_job(db, job_id, token)
        current_case = locked(db, Case, case.id)
        current_message = db.get(Message, message.id)
        db.add_all(proposed)
        current_message.status = "evaluated" if proposed else "needs_review"
        current_case.status = "data_review"
        job.status = "done"
        audit(
            db, "worker", "reply.evaluated", message.id, proposals=len(proposed), attachments=len(documents)
        )


def run_once(factory, settings):
    claimed = claim_job(factory)
    if not claimed:
        return False
    job_id, token, kind, target_id = claimed
    try:
        if kind == "send":
            send_job(factory, settings, job_id, token, target_id)
        elif kind == "evaluate":
            evaluate_job(factory, settings, job_id, token, target_id)
        else:
            raise ProviderUnavailable("Unknown job kind.")
    except Exception as exc:
        # Never log exception repr: provider exceptions can contain request bodies or API keys.
        error = (
            str(exc) if isinstance(exc, ProviderUnavailable) else "Processing failed; manual retry required."
        )
        with factory.begin() as db:
            job = db.get(Job, job_id)
            if job.status == "running" and job.claim_token == token:
                job.status, job.error = "failed", error
                if kind == "evaluate":
                    db.get(Message, target_id).status = "failed"
                audit(db, "worker", "job.failed", job_id, reason=error)
    return True


def main():
    settings = get_settings()
    factory = sessions(make_engine(settings.database_url))
    print("NOVA worker started; provider payloads and credentials are never logged.", flush=True)
    while True:
        if not run_once(factory, settings):
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
