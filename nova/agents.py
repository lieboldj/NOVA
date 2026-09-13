"""Workload summaries and paginated supplier histories for the two user-facing agents."""

from sqlalchemy import func, select

from nova.models import Audit, Case, Draft, Message, Proposal
from nova.workflow import fail, supplier_display_name

AGENTS = {
    "email": ("Email agent", Draft, ["sent", "simulated"], ["pending", "approved", "sending"]),
    "evaluation": (
        "Reply evaluation agent",
        Message,
        ["evaluated", "needs_review", "reviewed"],
        ["queued", "processing"],
    ),
}
EVENTS = [
    "email.drafted",
    "email.copy_refreshed",
    "email.sending",
    "email.sent",
    "email.simulated",
    "email.auto_approved",
    "email.rejection_followup_queued",
    "email.send_blocked",
    "email.send_uncertain",
    "reply.received",
    "reply.evaluation_failed",
    "reply.evaluation_started",
    "reply.evaluated",
    "reply.confidence_assessed",
]


def install_agent_routes(app, DB, Reviewer):
    @app.get("/agents", tags=["Operations"])
    def summaries(db: DB, actor: Reviewer):
        items = []
        for kind, (name, model, completed, active) in AGENTS.items():
            counts = dict(db.execute(select(model.status, func.count()).group_by(model.status)).all())
            suppliers = db.scalar(
                select(func.count(func.distinct(Case.supplier_id)))
                .select_from(model)
                .join(Case, model.case_id == Case.id)
            )
            items.append(
                {
                    "id": kind,
                    "name": name,
                    "total": sum(counts.values()),
                    "suppliers": suppliers,
                    "completed": sum(counts.get(status, 0) for status in completed),
                    "active": sum(counts.get(status, 0) for status in active),
                }
            )
        return items

    @app.get("/agents/{kind}/activity", tags=["Operations"])
    def history(kind: str, db: DB, actor: Reviewer, offset: int = 0, limit: int = 50):
        if kind not in AGENTS:
            fail("Agent not found", 404)
        if offset < 0 or not 1 <= limit <= 100:
            fail("Invalid pagination", 422)
        name, model, _, _ = AGENTS[kind]
        times = (
            select(Audit.entity_id, func.max(Audit.at).label("touched"))
            .where(Audit.action.in_(EVENTS))
            .group_by(Audit.entity_id)
            .subquery()
        )
        touched = func.coalesce(times.c.touched, model.created_at)
        query = (
            select(model, Case, touched.label("last_touched_at"))
            .join(Case, model.case_id == Case.id)
            .outerjoin(times, times.c.entity_id == model.id)
            .order_by(touched.desc(), model.id.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = db.execute(query).all()
        ids = [item.id for item, _, _ in rows]
        accepted = (
            dict(
                db.execute(
                    select(Proposal.message_id, func.count())
                    .where(
                        Proposal.message_id.in_(ids),
                        Proposal.reviewed_by == "confidence-agent",
                        Proposal.status == "approved",
                    )
                    .group_by(Proposal.message_id)
                ).all()
            )
            if kind == "evaluation"
            else {}
        )
        return {
            "agent": kind,
            "name": name,
            "total": db.scalar(select(func.count()).select_from(model)),
            "items": [
                {
                    "id": item.id,
                    "case_id": case.id,
                    "supplier_name": supplier_display_name(case.supplier_name),
                    "article": case.nart,
                    "status": item.status,
                    "last_touched_at": at,
                    "automatically_accepted": accepted.get(item.id, 0),
                    "work": ("Information request" if item.kind == "request" else "Supplier follow-up")
                    if kind == "email"
                    else "Supplier reply evaluation",
                }
                for item, case, at in rows
            ],
        }
