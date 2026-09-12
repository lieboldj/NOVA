from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    # UTC, stored without timezone for consistent SQLite/Postgres development behavior.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class ImportBatch(Base):
    __tablename__ = "imports"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    rows: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default="pending")
    created_at: Mapped[datetime] = mapped_column(default=now)


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("supplier_id", "nart", name="uq_case_supplier_article"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    supplier_id: Mapped[str]
    supplier_name: Mapped[str]
    nart: Mapped[str]
    recipient: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="open", index=True)
    revision: Mapped[int] = mapped_column(default=1)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime, default=now, index=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_reply_at: Mapped[datetime | None] = mapped_column(DateTime)
    reminders_sent: Mapped[int] = mapped_column(default=0)


class SupplierField(Base):
    __tablename__ = "supplier_fields"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(default=1)


class Draft(Base):
    __tablename__ = "email_drafts"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str]
    recipient: Mapped[str]
    subject: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    requested_fields: Mapped[list] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(default=1)
    case_revision: Mapped[int]
    status: Mapped[str] = mapped_column(default="pending", index=True)
    approved_digest: Mapped[str | None]
    approved_by: Mapped[str | None]
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    provider_id: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(default=now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    external_id: Mapped[str] = mapped_column(unique=True)
    sender: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    requested_fields: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default="queued")
    created_at: Mapped[datetime] = mapped_column(default=now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), index=True)
    filename: Mapped[str]
    content_type: Mapped[str]
    storage_key: Mapped[str]
    sha256: Mapped[str]


class Proposal(Base):
    __tablename__ = "change_proposals"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"))
    field_id: Mapped[str] = mapped_column(ForeignKey("supplier_fields.id"))
    old_value: Mapped[str] = mapped_column(Text)
    field_revision: Mapped[int]
    value: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON)
    rationale: Mapped[str] = mapped_column(Text)
    validation_errors: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default="pending", index=True)
    version: Mapped[int] = mapped_column(default=1)
    reviewed_by: Mapped[str | None]


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    kind: Mapped[str]
    target_id: Mapped[str]
    dedupe_key: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="queued", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(default=now, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    claim_token: Mapped[str | None]
    error: Mapped[str | None]


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    at: Mapped[datetime] = mapped_column(default=now)
    actor: Mapped[str]
    action: Mapped[str]
    entity_id: Mapped[str]
    details: Mapped[dict] = mapped_column(JSON, default=dict)
