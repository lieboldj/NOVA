"""Explicit policy exception: bounded automatic follow-ups, never automatic data approval."""

from sqlalchemy import func, select

from nova.models import Audit, Draft, Message, Proposal, SupplierField, now
from nova.workflow import (
    ACTIVE_DRAFTS,
    AI_DISCLOSURE,
    OUTSTANDING,
    audit,
    auto_approve_draft,
    blocking_message,
    draft_digest,
    enqueue,
    fail,
    field_guidance,
    invalidate_drafts,
    supplier_display_name,
    validate_value,
)

AUTO_ACTOR = "automation"


def still_authorized(db, settings, case, draft):
    if (
        not settings.auto_send_followups
        or not settings.auto_followup_enabled
        or draft.approved_by != AUTO_ACTOR
    ):
        return False
    marker = db.scalar(
        select(Audit).where(
            Audit.action == "email.auto_followup_planned",
            Audit.details["draft_id"].as_string() == draft.id,
        )
    )
    if not marker:
        return False
    source = db.get(Message, marker.entity_id)
    return bool(
        source
        and source.case_id == case.id
        and {f.id for f in unanswered_fields(db, case, source)} == set(draft.requested_fields)
    )


def unanswered_fields(db, case, message):
    fields = db.scalars(
        select(SupplierField)
        .where(SupplierField.case_id == case.id, SupplierField.id.in_(message.requested_fields))
        .order_by(SupplierField.id)
    ).all()
    unresolved = []
    for field in fields:
        if field.data["Status"] not in OUTSTANDING or field.data["Editable by supplier"].lower() != "yes":
            continue
        # A valid pending proposal counts as received, not as accepted supplier data.
        candidates = db.scalars(
            select(Proposal).where(
                Proposal.case_id == case.id,
                Proposal.field_id == field.id,
                Proposal.status.in_(["pending", "approved"]),
                Proposal.field_revision == field.revision,
            )
        ).all()
        if any(not p.validation_errors and not validate_value(field, p.value) for p in candidates):
            continue
        unresolved.append(field)
    return unresolved


def plan_followup(db, settings, case, message):
    if (
        not settings.auto_send_followups
        or not settings.auto_followup_enabled
        or message.status not in ("evaluated", "needs_review")
    ):
        return None
    if case.status in ("paused", "closed", "escalated") or not case.recipient:
        return None
    if case.recipient.casefold() != message.sender.casefold():
        return None
    if settings.mail_mode == "gmail" and case.recipient.casefold() != settings.gmail_supplier.casefold():
        return None
    # Case lock is held by evaluate_job. Do not react before all current evidence is processed.
    if db.scalar(
        select(Message.id)
        .where(Message.case_id == case.id, Message.status.in_(["queued", "processing", "failed"]))
        .limit(1)
    ):
        return None
    previous = db.scalar(
        select(Audit).where(Audit.action == "email.auto_followup_planned", Audit.entity_id == message.id)
    )
    if previous:
        return db.get(Draft, previous.details["draft_id"])
    if db.scalar(select(Draft.id).where(Draft.case_id == case.id, Draft.status.in_(ACTIVE_DRAFTS)).limit(1)):
        return None
    if not db.scalar(
        select(Draft.id)
        .where(
            Draft.case_id == case.id,
            Draft.status.in_(["sent", "simulated"]),
            Draft.recipient == case.recipient,
        )
        .limit(1)
    ):
        return None
    fields = unanswered_fields(db, case, message)
    if not fields:
        audit(
            db,
            AUTO_ACTOR,
            "reply.answers_received",
            message.id,
            requested_count=len(message.requested_fields),
        )
        return None
    rounds = db.scalar(
        select(func.count(Draft.id)).where(Draft.case_id == case.id, Draft.kind == "auto_followup")
    )
    if rounds >= max(0, min(settings.auto_followup_max_rounds, 10)):
        audit(db, AUTO_ACTOR, "email.auto_followup_limit", message.id, unresolved=[f.id for f in fields])
        return None
    lines = []
    for field in fields:
        data = field.data
        line = f"- [{field.id}] {data['Section']} — {data['Field (label)']}"
        if data["Field Type"] == "Date":
            line += "\n  Please provide a valid calendar date in YYYY-MM-DD format."
        if field.rules.get("options"):
            line += "\n  Accepted answers: " + "; ".join(field.rules["options"])
        if data["Field (label)"].strip() == "Reporting year":
            line += "\n  Please provide a four-digit reporting year."
        lines.append(line)
    body = (
        f"Let's stay compliant together.\n\nHello {supplier_display_name(case.supplier_name)},\n\nThank you for your reply. We still need a complete, valid answer "
        f"to the following {len(fields)} question(s) for article {case.nart or '(supplier level)'}. "
        "Please provide missing answers or clarify entries that do not meet the requested format. "
        "You do not need to repeat information already provided in a valid format. "
        "You may reply in this email thread and attach supporting documents.\n\n"
        + "\n".join(lines)
        + "\n\nThank you,\nSupplier Information Team\n\n"
        + AI_DISCLOSURE
    )
    draft = Draft(
        case_id=case.id,
        kind="auto_followup",
        recipient=case.recipient,
        subject="Your business partner has an information request",
        body=body,
        requested_fields=[f.id for f in fields],
        case_revision=case.revision,
        version=1,
    )
    db.add(draft)
    db.flush()
    auto_approve_draft(db, draft, settings)
    audit(
        db,
        AUTO_ACTOR,
        "email.auto_followup_planned",
        message.id,
        draft_id=draft.id,
        unresolved=draft.requested_fields,
        round=rounds + 1,
        policy="Missing or invalid answers only; supplier data still requires review",
    )
    case.status, case.next_action_at = "data_review", None
    return draft


def send_rejection_followup(db, settings, case, message, rejected, actor):
    """One immediate, durable email authorized by the submitted rejection decisions."""
    if not case.recipient and rejected:
        fail("Add a supplier email before submitting rejections", 422)
    if not case.recipient:
        return None
    # Preserve other rejected answers if an unsent correction request is replaced.
    prior_ids = set()
    prior_proposals = set()
    for draft in db.scalars(
        select(Draft).where(
            Draft.case_id == case.id,
            Draft.kind == "rejection_followup",
            Draft.status.in_(["pending", "approved"]),
        )
    ):
        prior_ids.update(draft.requested_fields)
        marker = db.scalar(
            select(Audit).where(
                Audit.entity_id == draft.id, Audit.action == "email.rejection_followup_queued"
            )
        )
        if marker:
            prior_proposals.update(marker.details.get("proposal_ids", []))
    if not rejected and not prior_ids:
        return None
    if settings.mail_mode == "gmail" and case.recipient.casefold() != settings.gmail_supplier.casefold():
        fail("Supplier contact is outside the configured Gmail recipient", 422)
    combined = {
        p.field_id: p
        for p in db.scalars(
            select(Proposal).where(
                Proposal.case_id == case.id, Proposal.id.in_(prior_proposals), Proposal.status == "rejected"
            )
        )
    }
    combined.update({p.field_id: p for p in rejected})
    lines = []
    requested = []
    for field_id, proposal in combined.items():
        field = db.get(SupplierField, field_id)
        if field.revision > proposal.field_revision and proposal not in rejected:
            continue
        reason = proposal.evidence.get("rejection_reason", "Please clarify this answer.")
        lines.append(
            f"- [{field.id}] {field.data['Field (label)']}\n"
            f"  You sent: {proposal.value}\n  {reason}\n  {field_guidance(field)}"
        )
        requested.append(field.id)
    if not requested:
        return None
    invalidate_drafts(db, case)
    draft = Draft(
        case_id=case.id,
        kind="rejection_followup",
        recipient=case.recipient,
        subject="Your business partner has an information request",
        body=(
            f"Let's stay compliant together.\n\nHello {supplier_display_name(case.supplier_name)},\n\n"
            f"Thank you for sharing your information for article {case.nart or '(supplier level)'}. "
            "We need your help to clarify a few answers before we can accept them:\n\n"
            + "\n\n".join(lines)
            + "\n\nPlease reply with the corrected details, and attach supporting documents if helpful. "
            "There’s no need to repeat the answers we’ve already accepted. "
            "If anything is unclear, let us know and we’ll help.\n\n"
            "Thank you for your help,\nSupplier Information Team\n\n" + AI_DISCLOSURE
        ),
        requested_fields=requested,
        case_revision=case.revision,
        version=1,
        status="approved",
        approved_by=actor,
        approved_at=now(),
    )
    db.add(draft)
    db.flush()
    draft.approved_digest = draft_digest(draft)
    enqueue(db, "send", draft.id, f"send:{draft.id}:{draft.version}")
    audit(
        db,
        actor,
        "email.rejection_followup_queued",
        draft.id,
        message_id=message.id,
        proposal_ids=[p.id for field_id, p in combined.items() if field_id in requested],
    )
    case.status = "data_review" if blocking_message(db, case.id) else "awaiting_reply"
    case.next_action_at = None
    return draft
