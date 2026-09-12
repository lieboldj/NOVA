import csv
import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from nova.models import Audit, Case, Draft, Job, Message, Proposal, SupplierField, now

CSV_COLUMNS = [
    "Row ID",
    "Supplier ID",
    "Supplier Name",
    "NART",
    "Use case",
    "Module (ID)",
    "Category",
    "Section",
    "Field (label)",
    "Field Type",
    "Required @ go-live",
    "Editable by supplier",
    "Value submitted",
    "Submission date",
    "Status",
]
V2_COLUMNS = CSV_COLUMNS[:3] + ["Country"] + CSV_COLUMNS[3:] + ["Workflow status", "Last contact date"]
TARGETING_COLUMNS = ["Region", "Industry"]
OUTSTANDING = {"Missing", "Outdated", "Flagged (needs supplier confirmation)"}
STATUSES = OUTSTANDING | {"Complete", "N/A (informational field)"}
ACTIVE_DRAFTS = ["pending", "approved", "sending", "uncertain"]


def fail(message: str, code: int = 409):
    raise HTTPException(code, message)


def locked(db, model, entity_id):
    obj = db.scalar(
        select(model).where(model.id == entity_id).with_for_update().execution_options(populate_existing=True)
    )
    if obj is None:
        fail("Record not found", 404)
    return obj


def locked_child(db, model, entity_id):
    # Use the same lock order as workers and scheduled checks: case before its children.
    obj = db.get(model, entity_id)
    if obj is None:
        fail("Record not found", 404)
    locked(db, Case, obj.case_id)
    return locked(db, model, entity_id)


def audit(db, actor, action, entity_id, **details):
    db.add(Audit(actor=actor, action=action, entity_id=entity_id, details=details))


def enqueue(db, kind, target_id, dedupe_key):
    existing = db.scalar(select(Job).where(Job.dedupe_key == dedupe_key))
    if existing:
        return existing
    job = Job(kind=kind, target_id=target_id, dedupe_key=dedupe_key)
    db.add(job)
    db.flush()
    return job


def parse_csv(content: bytes):
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        headers = reader.fieldnames or []
        base = [name for name in headers if name not in TARGETING_COLUMNS]
        if base not in [CSV_COLUMNS, V2_COLUMNS] or len(headers) != len(set(headers)):
            fail("CSV headers must match v1 or v2, with optional Region and Industry columns", 422)
        rows = list(reader)
    except (UnicodeError, csv.Error):
        fail("Invalid UTF-8 CSV", 422)
    if not rows or len(rows) > 100000:
        fail("Import requires 1–100,000 rows", 422)
    seen = set()
    names = {}
    for row in rows:
        if None in row or any(v is None for v in row.values()):
            fail("CSV contains inconsistent columns", 422)
        if not all(row[k].strip() for k in ["Row ID", "Supplier ID", "Supplier Name", "Field (label)"]):
            fail("Missing row identity or field label", 422)
        if row["Row ID"] in seen:
            fail("Duplicate Row ID in import", 422)
        seen.add(row["Row ID"])
        if row["Status"] not in STATUSES:
            fail("Unknown submission status", 422)
        sid = row["Supplier ID"]
        if sid in names and names[sid] != row["Supplier Name"]:
            fail("Conflicting names for one supplier ID", 422)
        names[sid] = row["Supplier Name"]
    return rows


def rules_catalog():
    path = Path(__file__).resolve().parent.parent / "Data_Collection.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    result = {}
    for r in rows:
        source = r["Dropdown / default source"].strip()
        options = []
        if r["Field Type"] == "Dropdown":
            if ";" in source:
                options = [s.strip() for s in source.split(";")]
            elif " / " in source or source == "Yes/No":
                options = [s.strip() for s in source.removeprefix("Fixed list: ").split("/")]
        key = tuple(r[k].strip() for k in ["Use cases", "Module (ID)", "Section", "Field (label)"])
        result[key] = {
            "options": options,
            "definition": r["Purpose / definition"],
            "validation": r["Validation / rules"],
        }
    return result


def validate_value(field, value):
    errors = []
    if value.strip().casefold() in {"", "tbd", "unknown", "pending", "n/a", "-"}:
        errors.append("A concrete answer is required; this looks like a placeholder.")
    options = field.rules.get("options", [])
    if options and value not in options:
        errors.append("Value must match one of the configured dropdown options.")
    if field.data["Field Type"] == "Date":
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            errors.append("Date must be a valid YYYY-MM-DD date.")
    if field.data["Field (label)"].strip() == "Reporting year" and not re.fullmatch(r"\d{4}", value):
        errors.append("Reporting year must contain four digits.")
    if field.data["Editable by supplier"].strip().lower() != "yes":
        errors.append("This field is not editable by the supplier.")
    return errors


def outstanding(db, case_id):
    return [
        f
        for f in db.scalars(
            select(SupplierField).where(SupplierField.case_id == case_id).order_by(SupplierField.id)
        )
        if f.data["Status"] in OUTSTANDING and f.data["Editable by supplier"].lower() == "yes"
    ]


def pending_review(db, case_id):
    return bool(
        db.scalar(select(Proposal.id).where(Proposal.case_id == case_id, Proposal.status == "pending"))
    )


def blocking_message(db, case_id):
    return bool(
        db.scalar(
            select(Message.id).where(
                Message.case_id == case_id,
                Message.status.in_(["queued", "processing", "failed", "needs_review", "evaluated"]),
            )
        )
    )


def draft_digest(draft):
    data = {k: getattr(draft, k) for k in ["recipient", "subject", "body", "requested_fields", "version"]}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def invalidate_drafts(db, case):
    for draft in db.scalars(
        select(Draft).where(Draft.case_id == case.id, Draft.status.in_(["pending", "approved"]))
    ):
        draft.status = "superseded"
    case.revision += 1


def create_draft(db, case, kind, use_case=None):
    if not case.recipient:
        fail("Approve a supplier email contact before drafting.")
    if pending_review(db, case.id) or blocking_message(db, case.id):
        fail("Review the supplier reply and pending changes first.")
    existing = db.scalar(select(Draft).where(Draft.case_id == case.id, Draft.status.in_(ACTIVE_DRAFTS)))
    if existing:
        return existing
    fields = outstanding(db, case.id)
    if use_case:
        fields = [f for f in fields if f.data["Use case"].strip().casefold() == use_case.casefold()]
    if not fields:
        fail("No outstanding fields.")
    heading = {
        "request": "Information request",
        "followup": "Outstanding information",
        "reminder": "Reminder",
    }[kind]
    if use_case:
        heading = f"{use_case} {heading}"
    lines = []
    for field in fields:
        d = field.data
        line = f"- [{field.id}] {d['Section']} — {d['Field (label)']} (status: {d['Status']})"
        if field.rules.get("options"):
            line += "\n  Accepted answers: " + "; ".join(field.rules["options"])
        lines.append(line)
    body = (
        f"Hello {case.supplier_name},\n\n"
        f"Please provide or confirm the following information for article {case.nart or '(supplier level)'}. "
        "You may reply in this email thread and attach supporting documents. "
        "Please include the field references shown below.\n\n"
        + "\n".join(lines)
        + "\n\nThank you,\nSupplier Information Team"
    )
    draft = Draft(
        case_id=case.id,
        kind=kind,
        recipient=case.recipient,
        subject=f"[NOVA:{case.id}] {heading}",
        body=body,
        requested_fields=[f.id for f in fields],
        case_revision=case.revision,
    )
    db.add(draft)
    case.status = "email_review"
    case.next_action_at = None
    db.flush()
    audit(db, "backend", "email.drafted", draft.id, kind=kind)
    return draft


def tick(db, settings):
    counts = {"drafted": 0, "closed": 0, "escalated": 0, "skipped": 0}
    cases = db.scalars(
        select(Case)
        .where(Case.next_action_at <= now(), Case.status.not_in(["closed", "escalated"]))
        .with_for_update(skip_locked=True)
    ).all()
    for case in cases:
        if not case.recipient or pending_review(db, case.id) or blocking_message(db, case.id):
            counts["skipped"] += 1
            continue
        if db.scalar(select(Draft.id).where(Draft.case_id == case.id, Draft.status.in_(ACTIVE_DRAFTS))):
            counts["skipped"] += 1
            continue
        if not outstanding(db, case.id):
            case.status, case.next_action_at = "closed", None
            counts["closed"] += 1
            continue
        replied = case.last_reply_at and case.last_sent_at and case.last_reply_at > case.last_sent_at
        kind = "request" if not case.last_sent_at else "followup" if replied else "reminder"
        if kind == "reminder" and case.reminders_sent >= settings.max_reminders:
            case.status, case.next_action_at = "escalated", None
            audit(db, "backend", "case.escalated", case.id)
            counts["escalated"] += 1
            continue
        create_draft(db, case, kind)
        counts["drafted"] += 1
    return counts
