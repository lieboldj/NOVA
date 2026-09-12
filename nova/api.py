import csv
import io
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from nova.browser import browser_actor, install_browser
from nova.config import get_settings
from nova.db import initialize, make_engine, sessions
from nova.gmail import Gmail, install_gmail_routes
from nova.inbox import ingest_message
from nova.initiation import install_initiation_routes
from nova.models import (
    Audit,
    Case,
    Document,
    Draft,
    ImportBatch,
    Job,
    Message,
    Proposal,
    SupplierField,
    now,
)
from nova.schemas import (
    Approval,
    ContactApproval,
    DraftEdit,
    ImportApproval,
    ProposalEdit,
    SendReconciliation,
)
from nova.workflow import (
    CSV_COLUMNS,
    OUTSTANDING,
    TARGETING_COLUMNS,
    V2_COLUMNS,
    audit,
    blocking_message,
    create_draft,
    draft_digest,
    enqueue,
    fail,
    invalidate_drafts,
    locked,
    locked_child,
    outstanding,
    parse_csv,
    pending_review,
    rules_catalog,
    tick,
    validate_value,
)

bearer = HTTPBearer(auto_error=False)


def record(obj):
    return {c.key: getattr(obj, c.key) for c in inspect(type(obj)).column_attrs}


def authorize(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if not credentials:
        return browser_actor(request)
    settings = request.app.state.settings
    for role, token in [
        ("reviewer", settings.nova_reviewer_token),
        ("automation", settings.nova_automation_token),
    ]:
        expected = token.get_secret_value()
        if expected and secrets.compare_digest(credentials.credentials, expected):
            return settings.nova_reviewer_name if role == "reviewer" else "automation"
    fail("Invalid credentials", 401)


def reviewer(request: Request, actor: Annotated[str, Depends(authorize)]):
    if actor == "automation":
        fail("Human reviewer credentials required", 403)
    return actor


def database(request: Request):
    with request.app.state.factory.begin() as db:
        try:
            yield db
        except IntegrityError:
            fail("Conflicting or duplicate record; reload and retry", 409)


DB = Annotated[object, Depends(database, scope="function")]
Reviewer = Annotated[str, Depends(reviewer)]
Operator = Annotated[str, Depends(authorize)]


def finish_review(db, case):
    db.flush()
    if not pending_review(db, case.id):
        if outstanding(db, case.id):
            case.status, case.next_action_at = "open", now()
        else:
            case.status, case.next_action_at = "closed", None


def proposal_errors(db, proposal, field, value):
    errors = validate_value(field, value)
    if "upload" in field.data["Field Type"].lower():
        doc = db.get(Document, value.removeprefix("document://")) if value.startswith("document://") else None
        if not doc or doc.message_id != proposal.message_id:
            errors.append("File value must reference a document attached to this reply.")
    return errors


def create_app(settings=None, engine=None):
    settings = settings or get_settings()
    engine = engine or make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        settings.storage_path.mkdir(parents=True, exist_ok=True)
        # Production PostgreSQL is migrated explicitly with Alembic before starting services.
        if settings.database_url.startswith("sqlite"):
            initialize(engine)
        reviewer_key = settings.nova_reviewer_token.get_secret_value()
        automation_key = settings.nova_automation_token.get_secret_value()
        if not reviewer_key or not automation_key or reviewer_key == automation_key:
            raise RuntimeError("Configure distinct NOVA_REVIEWER_TOKEN and NOVA_AUTOMATION_TOKEN secrets.")
        if settings.nova_reviewer_name == "automation":
            raise RuntimeError("Reviewer identity must differ from automation.")
        if settings.anonymizer_mode == "fixture" and settings.ai_mode != "fixture":
            raise RuntimeError("Remote models require Anymize sanitization.")
        yield

    app = FastAPI(
        title="NOVA Backend",
        version="0.1.0",
        lifespan=lifespan,
        description="Supplier follow-up API. Emails and supplier data changes require human approval.",
    )
    app.state.settings, app.state.engine = settings, engine
    app.state.factory = sessions(engine)
    install_initiation_routes(app, settings, DB, Reviewer)

    @app.get("/health", tags=["Operations"])
    def health():
        return {"status": "ok"}

    @app.get("/configuration", tags=["Operations"])
    def configuration(actor: Reviewer):
        return {
            "ai_mode": settings.ai_mode,
            "anonymizer_mode": settings.anonymizer_mode,
            "mail_mode": settings.mail_mode,
            "gmail_mailbox": settings.gmail_mailbox,
            "gmail_supplier": settings.gmail_supplier,
            "gmail_configured": Gmail.configured(settings),
            "gemini_configured": bool(settings.gemini_api_key.get_secret_value()),
            "anymize_configured": bool(settings.anymize_api_key.get_secret_value()),
            "response_days": settings.response_days,
            "max_reminders": settings.max_reminders,
        }

    @app.post("/imports", tags=["Imports"], status_code=201)
    async def preview_import(db: DB, actor: Reviewer, file: UploadFile = File()):
        content = await file.read(settings.import_limit_bytes + 1)
        if len(content) > settings.import_limit_bytes:
            fail("File exceeds upload limit", 413)
        batch = ImportBatch(rows=parse_csv(content))
        db.add(batch)
        db.flush()
        audit(db, actor, "import.proposed", batch.id, rows=len(batch.rows))
        return {
            "id": batch.id,
            "status": batch.status,
            "row_count": len(batch.rows),
            "suppliers": sorted({r["Supplier ID"] for r in batch.rows}),
        }

    @app.get("/imports/{batch_id}", tags=["Imports"])
    def get_import(batch_id: str, db: DB, actor: Reviewer):
        return record(locked(db, ImportBatch, batch_id))

    @app.post("/imports/{batch_id}/approve", tags=["Imports"])
    def approve_import(batch_id: str, body: ImportApproval, db: DB, actor: Reviewer):
        batch = locked(db, ImportBatch, batch_id)
        if batch.status == "approved":
            return {"id": batch.id, "status": batch.status}
        if batch.status != "pending":
            fail("Import is no longer pending")
        ids = [r["Row ID"] for r in batch.rows]
        for start in range(0, len(ids), 1000):
            if db.scalar(
                select(SupplierField.id).where(SupplierField.id.in_(ids[start : start + 1000])).limit(1)
            ):
                fail("Import overlaps existing Row IDs; existing records cannot be overwritten by import.")
        catalog = rules_catalog()
        groups = {}
        for row in batch.rows:
            key = (row["Supplier ID"], row["NART"])
            if key not in groups:
                case = db.scalar(
                    select(Case).where(Case.supplier_id == key[0], Case.nart == key[1]).with_for_update()
                )
                if case:
                    invalidate_drafts(db, case)
                    case.status, case.next_action_at = "open", now()
                else:
                    case = Case(
                        supplier_id=key[0],
                        nart=key[1],
                        supplier_name=row["Supplier Name"],
                        recipient=str(body.contacts.get(key[0], "")),
                    )
                    db.add(case)
                    db.flush()
                groups[key] = case
            rule_key = tuple(row[k].strip() for k in ["Use case", "Module (ID)", "Section", "Field (label)"])
            db.add(
                SupplierField(
                    id=row["Row ID"], case_id=groups[key].id, data=row, rules=catalog.get(rule_key, {})
                )
            )
        batch.status = "approved"
        audit(db, actor, "import.approved", batch.id, rows=len(batch.rows))
        return {"id": batch.id, "status": batch.status, "case_ids": [c.id for c in groups.values()]}

    @app.get("/cases", tags=["Cases"])
    def cases(db: DB, actor: Reviewer, offset: int = 0, limit: int = 100):
        if offset < 0 or not 1 <= limit <= 500:
            fail("Invalid pagination", 422)
        page = db.scalars(select(Case).order_by(Case.id).offset(offset).limit(limit)).all()
        counts = dict(
            db.execute(
                select(SupplierField.case_id, func.count(SupplierField.id))
                .where(
                    SupplierField.case_id.in_([c.id for c in page]),
                    SupplierField.data["Status"].as_string().in_(OUTSTANDING),
                    func.lower(SupplierField.data["Editable by supplier"].as_string()) == "yes",
                )
                .group_by(SupplierField.case_id)
            ).all()
        )
        return [record(c) | {"outstanding_count": counts.get(c.id, 0)} for c in page]

    @app.get("/cases/{case_id}", tags=["Cases"])
    def case_detail(case_id: str, db: DB, actor: Reviewer):
        case = locked(db, Case, case_id)
        return record(case) | {
            "fields": [
                record(f)
                for f in db.scalars(
                    select(SupplierField).where(SupplierField.case_id == case.id).order_by(SupplierField.id)
                )
            ]
        }

    @app.get("/cases/{case_id}/messages", tags=["Replies"])
    def case_messages(case_id: str, db: DB, actor: Reviewer):
        locked(db, Case, case_id)
        messages = db.scalars(
            select(Message).where(Message.case_id == case_id).order_by(Message.created_at.desc())
        ).all()
        return [
            record(m)
            | {
                "documents": [
                    record(d) for d in db.scalars(select(Document).where(Document.message_id == m.id))
                ]
            }
            for m in messages
        ]

    @app.get("/cases/{case_id}/activity", tags=["Cases"])
    def case_activity(case_id: str, db: DB, actor: Reviewer):
        locked(db, Case, case_id)
        entities = [case_id]
        for model in [Draft, Message, Proposal]:
            entities.extend(db.scalars(select(model.id).where(model.case_id == case_id)))
        return [
            record(a)
            for a in db.scalars(
                select(Audit).where(Audit.entity_id.in_(entities)).order_by(Audit.at.desc()).limit(200)
            )
        ]

    @app.post("/cases/{case_id}/contact/approve", tags=["Cases"])
    def contact(case_id: str, body: ContactApproval, db: DB, actor: Reviewer):
        case = locked(db, Case, case_id)
        if case.revision != body.revision:
            fail("Case changed; reload before approving contact")
        invalidate_drafts(db, case)
        case.recipient = str(body.recipient)
        case.next_action_at = now()
        audit(db, actor, "contact.approved", case.id)
        return record(case)

    @app.post("/automation/tick", tags=["Automation"])
    def automation_tick(db: DB, actor: Operator):
        result = tick(db, settings)
        audit(db, actor, "automation.tick", "scheduler", **result)
        return result

    @app.post("/cases/{case_id}/draft", tags=["Email"])
    def draft_case(case_id: str, db: DB, actor: Reviewer):
        case = locked(db, Case, case_id)
        kind = (
            "request"
            if not case.last_sent_at
            else "followup"
            if (case.last_reply_at and case.last_reply_at > case.last_sent_at)
            else "reminder"
        )
        return record(create_draft(db, case, kind))

    @app.get("/drafts", tags=["Email"])
    def drafts(db: DB, actor: Reviewer, case_id: str | None = None):
        query = select(Draft).order_by(Draft.created_at.desc()).limit(500)
        if case_id:
            query = query.where(Draft.case_id == case_id)
        return [record(d) for d in db.scalars(query)]

    @app.patch("/drafts/{draft_id}", tags=["Email"])
    def edit_draft(draft_id: str, body: DraftEdit, db: DB, actor: Reviewer):
        draft = locked_child(db, Draft, draft_id)
        case = locked(db, Case, draft.case_id)
        if draft.version != body.version or draft.status not in ["pending", "approved"]:
            fail("Draft changed or cannot be edited")
        if draft.case_revision != case.revision:
            fail("Case changed; create a fresh draft")
        if "\r" in body.subject or "\n" in body.subject:
            fail("Subject cannot contain line breaks", 422)
        draft.subject, draft.body = body.subject, body.body
        draft.version += 1
        draft.status = "pending"
        draft.approved_by = draft.approved_digest = draft.approved_at = None
        audit(db, actor, "email.edited", draft.id, version=draft.version)
        return record(draft)

    @app.post("/drafts/{draft_id}/approve", tags=["Email"])
    def approve_draft(draft_id: str, body: Approval, db: DB, actor: Reviewer):
        draft = locked_child(db, Draft, draft_id)
        case = locked(db, Case, draft.case_id)
        if draft.version != body.version or draft.case_revision != case.revision:
            fail("Draft or case changed; review the current version")
        if draft.status in ["approved", "sending", "sent", "simulated"]:
            return record(draft)
        if draft.status != "pending":
            fail("Draft is no longer pending")
        draft.status, draft.approved_by, draft.approved_at = "approved", actor, now()
        draft.approved_digest = draft_digest(draft)
        enqueue(db, "send", draft.id, f"send:{draft.id}:{draft.version}")
        audit(db, actor, "email.approved", draft.id, version=draft.version, digest=draft.approved_digest)
        return record(draft)

    @app.post("/drafts/{draft_id}/reject", tags=["Email"])
    def reject_draft(draft_id: str, body: Approval, db: DB, actor: Reviewer):
        draft = locked_child(db, Draft, draft_id)
        case = locked(db, Case, draft.case_id)
        if draft.version != body.version or draft.status not in ["pending", "approved"]:
            fail("Draft changed or cannot be rejected")
        draft.status, case.status, case.next_action_at = "rejected", "paused", None
        audit(db, actor, "email.rejected", draft.id, version=draft.version)
        return record(draft)

    @app.post("/cases/{case_id}/messages", tags=["Replies"], status_code=201)
    async def receive_message(
        case_id: str,
        db: DB,
        actor: Operator,
        external_id: str = Form(),
        sender: str = Form(),
        body: str = Form(""),
        attachments: list[UploadFile] = File(default=[]),
    ):
        uploads = []
        total = len(body.encode())
        if len(attachments) > 10:
            fail("Message exceeds input limits", 422)
        for file in attachments:
            data = await file.read(settings.upload_limit_bytes + 1)
            total += len(data)
            if total > settings.upload_limit_bytes:
                fail("Message exceeds upload limit", 413)
            uploads.append((file.filename or "attachment", data))
        return ingest_message(db, settings, case_id, external_id, sender, body, uploads, actor)

    @app.post("/drafts/{draft_id}/reconcile", tags=["Email"])
    def reconcile_send(draft_id: str, body: SendReconciliation, db: DB, actor: Reviewer):
        draft = locked_child(db, Draft, draft_id)
        case = locked(db, Case, draft.case_id)
        if draft.status != "uncertain" or draft.version != body.version:
            fail("Only the current uncertain send can be reconciled")
        if body.outcome == "sent":
            if not body.provider_id or not body.sent_at or not body.sent_at.tzinfo:
                fail("Provide the confirmed provider message ID and timezone-aware sending time", 422)
            sent_at = body.sent_at.astimezone(timezone.utc).replace(tzinfo=None)
            if sent_at > now():
                fail("Sending time cannot be in the future", 422)
            draft.status, draft.provider_id = "sent", body.provider_id
            case.last_sent_at = sent_at
            if not outstanding(db, case.id):
                case.status, case.next_action_at = "closed", None
            elif pending_review(db, case.id) or blocking_message(db, case.id):
                case.status, case.next_action_at = "data_review", None
            elif case.last_reply_at and case.last_reply_at > sent_at:
                case.status, case.next_action_at = "open", now()
            else:
                case.next_action_at = sent_at + timedelta(days=settings.response_days)
                case.status = "awaiting_reply"
            if draft.kind == "reminder":
                case.reminders_sent += 1
        else:
            draft.status = "pending" if draft.case_revision == case.revision else "superseded"
            draft.version += 1
            draft.approved_by = draft.approved_digest = draft.approved_at = None
            if draft.status == "pending":
                case.status, case.next_action_at = "email_review", None
            else:
                finish_review(db, case)
        audit(db, actor, "email.reconciled", draft.id, outcome=body.outcome, note=body.note)
        return record(draft)

    @app.get("/messages/{message_id}", tags=["Replies"])
    def message_detail(message_id: str, db: DB, actor: Reviewer):
        message = locked_child(db, Message, message_id)
        return record(message) | {
            "documents": [
                record(d) for d in db.scalars(select(Document).where(Document.message_id == message.id))
            ]
        }

    @app.post("/messages/{message_id}/review-complete", tags=["Replies"])
    def review_message(message_id: str, db: DB, actor: Reviewer):
        message = locked_child(db, Message, message_id)
        case = locked(db, Case, message.case_id)
        if message.status not in ["needs_review", "evaluated", "failed"]:
            fail("Reply processing is still active")
        if pending_review(db, case.id):
            fail("Approve or reject pending proposals first")
        message.status = "reviewed"
        finish_review(db, case)
        audit(db, actor, "reply.reviewed", message.id)
        return record(message)

    @app.get("/documents/{document_id}", tags=["Replies"])
    def document(document_id: str, db: DB, actor: Reviewer):
        doc = locked(db, Document, document_id)
        return FileResponse(
            settings.storage_path / doc.storage_key,
            media_type=doc.content_type,
            filename=doc.filename,
            content_disposition_type="attachment",
        )

    @app.get("/proposals", tags=["Data review"])
    def proposals(db: DB, actor: Reviewer, case_id: str | None = None):
        query = select(Proposal).order_by(Proposal.id).limit(1000)
        if case_id:
            query = query.where(Proposal.case_id == case_id)
        return [record(p) for p in db.scalars(query)]

    @app.patch("/proposals/{proposal_id}", tags=["Data review"])
    def edit_proposal(proposal_id: str, body: ProposalEdit, db: DB, actor: Reviewer):
        proposal = locked_child(db, Proposal, proposal_id)
        locked(db, Case, proposal.case_id)
        if proposal.version != body.version or proposal.status != "pending":
            fail("Proposal changed or is no longer pending")
        field = db.get(SupplierField, proposal.field_id)
        proposal.value = body.value
        proposal.version += 1
        proposal.validation_errors = proposal_errors(db, proposal, field, body.value)
        audit(db, actor, "change.edited", proposal.id, version=proposal.version)
        return record(proposal)

    @app.post("/proposals/{proposal_id}/approve", tags=["Data review"])
    def approve_proposal(proposal_id: str, body: Approval, db: DB, actor: Reviewer):
        proposal = locked_child(db, Proposal, proposal_id)
        case = locked(db, Case, proposal.case_id)
        field = locked(db, SupplierField, proposal.field_id)
        if proposal.version != body.version:
            fail("Proposal changed; review the current version")
        if proposal.status == "approved":
            return record(proposal)
        if proposal.status != "pending" or field.revision != proposal.field_revision:
            fail("Underlying data changed; this proposal cannot be applied")
        errors = proposal_errors(db, proposal, field, proposal.value)
        if errors or proposal.validation_errors:
            fail("Resolve validation errors before approval", 422)
        before = field.data.copy()
        field.data = before | {
            "Value submitted": proposal.value,
            "Status": "Complete",
            "Submission date": db.get(Message, proposal.message_id).created_at.date().isoformat(),
        }
        if "Workflow status" in before:
            field.data = field.data | {"Workflow status": "Closed"}
        field.revision += 1
        proposal.status, proposal.reviewed_by = "approved", actor
        invalidate_drafts(db, case)
        audit(
            db,
            actor,
            "change.approved",
            proposal.id,
            field_id=field.id,
            before=before,
            after=field.data,
            evidence=proposal.evidence,
        )
        finish_review(db, case)
        return record(proposal)

    @app.post("/proposals/{proposal_id}/reject", tags=["Data review"])
    def reject_proposal(proposal_id: str, body: Approval, db: DB, actor: Reviewer):
        proposal = locked_child(db, Proposal, proposal_id)
        case = locked(db, Case, proposal.case_id)
        if proposal.version != body.version or proposal.status != "pending":
            fail("Proposal changed or is no longer pending")
        proposal.status, proposal.reviewed_by = "rejected", actor
        audit(db, actor, "change.rejected", proposal.id)
        finish_review(db, case)
        return record(proposal)

    @app.get("/exports/submissions.csv", tags=["Exports"])
    def export_csv(db: DB, actor: Reviewer):
        output = io.StringIO(newline="")
        fields = db.scalars(select(SupplierField).order_by(SupplierField.id)).all()
        columns = V2_COLUMNS if any("Country" in f.data for f in fields) else CSV_COLUMNS
        columns = columns + [key for key in TARGETING_COLUMNS if any(key in f.data for f in fields)]
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for field in fields:
            writer.writerow(field.data)
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="supplier_submissions.csv"'},
        )

    @app.get("/jobs", tags=["Operations"])
    def jobs(db: DB, actor: Reviewer, case_id: str | None = None):
        query = select(Job)
        if case_id:
            targets = list(db.scalars(select(Draft.id).where(Draft.case_id == case_id)))
            targets.extend(db.scalars(select(Message.id).where(Message.case_id == case_id)))
            query = query.where(Job.target_id.in_(targets))
        return [record(j) for j in db.scalars(query.order_by(Job.available_at.desc()).limit(500))]

    @app.post("/jobs/{job_id}/retry", tags=["Operations"])
    def retry_job(job_id: str, db: DB, actor: Reviewer):
        job = locked(db, Job, job_id)
        if job.kind == "send" and job.status == "failed":
            draft = locked_child(db, Draft, job.target_id)
            if (
                draft.status != "approved"
                or job.error != "Gmail did not send; check configuration and retry."
            ):
                fail("Uncertain sends require manual reconciliation")
            job.status, job.error, job.available_at = "queued", None, now()
            audit(db, actor, "job.retried", job.id)
            return record(job)
        if job.kind != "evaluate" or job.status != "failed":
            fail(
                "Only failed evaluations can be retried; uncertain email sends require manual reconciliation"
            )
        message = locked(db, Message, job.target_id)
        if message.status != "failed":
            fail("Reply already reviewed; retry is no longer available")
        message.status = "queued"
        job.status, job.error, job.available_at = "queued", None, now()
        audit(db, actor, "job.retried", job.id)
        return record(job)

    @app.get("/audit", tags=["Operations"])
    def audit_events(db: DB, actor: Reviewer):
        return [record(a) for a in db.scalars(select(Audit).order_by(Audit.at.desc()).limit(500))]

    install_gmail_routes(app, settings, Reviewer, Operator)
    install_browser(app, settings, Reviewer)
    return app


app = create_app()
