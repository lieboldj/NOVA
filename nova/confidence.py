"""Evidence-based confidence and the explicitly authorized automatic acceptance policy."""

import re

from sqlalchemy import select

from nova.models import Document, Proposal, SupplierField
from nova.workflow import audit, invalidate_drafts, validate_value

POLICY = "evidence-confidence-v2"
THRESHOLD = 0.90


def normalized(value):
    return re.sub(r"\s+", " ", value).strip().casefold()


def assess(field, proposal, source_text="", *, conflict=False, ambiguous_label=False):
    evidence = proposal.evidence
    model = evidence.get("model_confidence", evidence.get("confidence"))
    mapping = evidence.get("mapping_confidence")
    value, quote = normalized(proposal.value), normalized(evidence.get("quote", ""))
    errors = list(dict.fromkeys(proposal.validation_errors + validate_value(field, proposal.value)))
    if not value or value in {"unknown", "tbd", "pending", "n/a", "-"}:
        return 0.0, "No concrete answer was received."
    if errors:
        return 0.25, "The answer does not meet the requested format or evidence requirements."
    if field.revision != proposal.field_revision:
        return 0.35, "The saved data has changed since this answer was received."
    if conflict:
        return 0.45, "Different unresolved answers were received for this data point."
    if not quote or not evidence.get("source_id"):
        return 0.15, "Supporting evidence is missing."
    if re.search(r"\b(maybe|might|not sure|uncertain|to be confirmed)\b", value):
        return 0.60, "The supplier's answer is tentative or incomplete."
    if evidence.get("spelling_correction"):
        return 0.80, "A possible spelling correction needs a decision."
    is_file = "upload" in field.data.get("Field Type", "").lower()
    supported = value in quote or (is_file and evidence.get("document_id"))
    if not supported:
        return 0.55, "The extracted value needs comparison with the original evidence."
    # Check only the answer's own line, not an unrelated label elsewhere in the email.
    label = normalized(field.data["Field (label)"])
    reference = normalized(field.id)
    lines = [quote] + [normalized(line) for line in source_text.splitlines()]
    explicit = any(
        (value in line or (is_file and line == quote))
        and any(
            re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", line)
            for key in (reference, "" if ambiguous_label else label)
            if key
        )
        for line in lines
    )
    if explicit:
        score = min(0.97, model) if model is not None else 0.97
        reason = "The answer is explicitly linked to this data point and passes format checks."
    elif model is not None and mapping is not None:
        score = min(model, mapping, 0.96)
        reason = "The agent matched the supporting evidence to the requested category and checked the format."
    else:
        score = min(model, 0.80) if model is not None else 0.65
        reason = "An answer was received, but its match to the requested category needs confirmation."
    return round(max(0.0, score), 3), reason


def missing_answers(db, message):
    if message.status in ("queued", "processing", "failed"):
        return []
    received = set(db.scalars(select(Proposal.field_id).where(Proposal.message_id == message.id)))
    return [
        {
            "field_id": field.id,
            "label": field.data["Field (label)"],
            "confidence": 0,
            "confidence_reason": "No answer was received for this requested data point.",
            "data": field.data,
        }
        for field in db.scalars(
            select(SupplierField)
            .where(SupplierField.case_id == message.case_id, SupplierField.id.in_(message.requested_fields))
            .order_by(SupplierField.id)
        )
        if field.id not in received
    ]


def apply_confidence(db, case, message, settings, *, sources=None, complete_reply=False):
    """Caller holds the case lock. Scoring, accepted values and audit commit together."""
    proposals = db.scalars(
        select(Proposal)
        .where(Proposal.message_id == message.id, Proposal.status == "pending")
        .order_by(Proposal.id)
    ).all()
    accepted = 0
    for proposal in proposals:
        field = db.get(SupplierField, proposal.field_id)
        alternatives = db.scalars(
            select(Proposal).where(
                Proposal.field_id == field.id,
                Proposal.status == "pending",
                Proposal.field_revision == field.revision,
                Proposal.id != proposal.id,
            )
        ).all()
        conflict = any(normalized(other.value) != normalized(proposal.value) for other in alternatives)
        evidence = proposal.evidence
        source = (sources or {}).get(evidence.get("source_id"), "")
        if evidence.get("source_id") == "email":
            source = message.body
        if evidence.get("document_id"):
            doc = db.get(Document, evidence["document_id"])
            if not doc or doc.message_id != message.id:
                proposal.validation_errors = list(
                    dict.fromkeys(
                        proposal.validation_errors + ["The evidence document does not belong to this reply."]
                    )
                )
        ambiguous_label = any(
            other.id != field.id
            and normalized(other.data["Field (label)"]) == normalized(field.data["Field (label)"])
            for other in db.scalars(select(SupplierField).where(SupplierField.case_id == case.id))
        )
        score, reason = assess(field, proposal, source, conflict=conflict, ambiguous_label=ambiguous_label)
        proposal.evidence = evidence | {
            "model_confidence": evidence.get("model_confidence", evidence.get("confidence")),
            "confidence": score,
            "confidence_reason": reason,
            "confidence_policy": POLICY,
        }
        if (
            not settings.auto_accept_high_confidence
            or score <= THRESHOLD
            or message.status not in ("evaluated", "needs_review")
        ):
            continue
        before = field.data.copy()
        field.data = before | {
            "Value submitted": proposal.value,
            "Status": "Complete",
            "Submission date": message.created_at.date().isoformat(),
        }
        if "Workflow status" in before:
            field.data = field.data | {"Workflow status": "Closed"}
        field.revision += 1
        proposal.status, proposal.reviewed_by = "approved", "confidence-agent"
        accepted += 1
        audit(
            db,
            "confidence-agent",
            "change.auto_approved",
            proposal.id,
            field_id=field.id,
            before=before,
            after=field.data,
            confidence=score,
            reason=reason,
            policy=POLICY,
            evidence=proposal.evidence,
        )
    db.flush()
    if accepted:
        # Preserve correction requests for other answers that still need clarification.
        from nova.followups import send_rejection_followup

        if not send_rejection_followup(db, settings, case, message, [], "confidence-agent"):
            invalidate_drafts(db, case)
    if (
        complete_reply
        and proposals
        and all(p.status == "approved" for p in proposals)
        and not missing_answers(db, message)
    ):
        message.status = "reviewed"
        audit(db, "confidence-agent", "reply.auto_reviewed", message.id, policy=POLICY)
    if proposals:
        audit(
            db,
            "confidence-agent",
            "reply.confidence_assessed",
            message.id,
            scored=len(proposals),
            automatically_accepted=accepted,
            policy=POLICY,
        )
    return {"scored": len(proposals), "automatically_accepted": accepted}
