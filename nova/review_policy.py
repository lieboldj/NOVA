"""Refresh existing pending reviews and generated unsent emails after a policy release.

Run with the deployed worker's environment: python -m nova.review_policy.
No reply is re-ingested, and no new supplier email is sent by this command.
"""

import json
import re

from sqlalchemy import select

from nova.confidence import POLICY, apply_confidence
from nova.config import get_settings
from nova.db import make_engine, sessions
from nova.models import Case, Draft, Message, Proposal, SupplierField
from nova.workflow import audit, locked


def refresh_pending_email_copy(db, case):
    changed = 0
    for draft in db.scalars(select(Draft).where(Draft.case_id == case.id, Draft.status == "pending")):
        if "Supplier Information Team" not in draft.body:
            continue  # Preserve custom reviewer-written messages.
        if not (
            draft.subject == "Your business partner has an information request"
            or re.match(r"\[NOVA:[0-9a-f-]+\]", draft.subject)
        ):
            continue
        subject = "Your business partner has an information request"
        body = draft.body
        for opening in ("Let's stay compliant together.", "Let us stay compliant together."):
            if body.startswith(opening):
                body = body[len(opening) :].lstrip()
                break
        body = "Let us stay compliant together.\n\n" + body
        for field in db.scalars(select(SupplierField).where(SupplierField.case_id == case.id)):
            body = re.sub(r"(?m)^- \[" + re.escape(field.id) + r"\]\s*", "- ", body)
        body = body.replace(
            "Please include the field references shown below.",
            "Please use the question names below when replying.",
        )
        # Old generated greetings can still contain the demo display prefix.
        body = re.sub(r"(?im)^Hello Demo\s+", "Hello ", body)
        if (subject, body) == (draft.subject, draft.body):
            continue
        draft.subject, draft.body = subject, body
        draft.version += 1
        draft.approved_by = draft.approved_digest = draft.approved_at = None
        audit(db, "backend", "email.copy_refreshed", draft.id, version=draft.version)
        changed += 1
    return changed


def refresh(factory, settings):
    from nova.workflow import finish_review

    totals = {"scored": 0, "automatically_accepted": 0, "email_templates_updated": 0}
    with factory() as db:
        ids = list(db.scalars(select(Case.id).order_by(Case.id)))
    for case_id in ids:
        with factory.begin() as db:
            case = locked(db, Case, case_id)
            pending = db.scalars(
                select(Proposal).where(Proposal.case_id == case_id, Proposal.status == "pending")
            ).all()
            message_ids = {p.message_id for p in pending if p.evidence.get("confidence_policy") != POLICY}
            changed = False
            for message_id in sorted(message_ids):
                message = db.get(Message, message_id)
                if message.status not in ("evaluated", "needs_review"):
                    continue
                result = apply_confidence(db, case, message, settings)
                for key, value in result.items():
                    totals[key] += value
                changed = True
            if changed:
                finish_review(db, case)
            totals["email_templates_updated"] += refresh_pending_email_copy(db, case)
    return totals


def main():
    settings = get_settings()
    factory = sessions(make_engine(settings.database_url))
    print(json.dumps(refresh(factory, settings)), flush=True)


if __name__ == "__main__":
    main()
