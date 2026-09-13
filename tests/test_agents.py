from datetime import datetime, timedelta

from nova.models import Audit, Draft, Job, Message
from tests.conftest import AUTOMATION, REVIEW, request_draft, seed


def test_agents_are_two_workload_summaries_and_history_uses_actual_activity(env):
    client, factory, _ = env
    case = seed(client)
    initial = request_draft(client, case)
    with factory.begin() as db:
        first = db.get(Draft, initial["id"])
        first.created_at = datetime(2020, 1, 1)
        first.status = "sent"
        newer = Draft(
            case_id=case,
            kind="followup",
            recipient="supplier@example.com",
            subject="Request",
            body="Request",
            requested_fields=["F1"],
            case_revision=1,
            created_at=datetime(2021, 1, 1),
        )
        db.add(newer)
        db.flush()
        db.add(
            Audit(
                actor="worker", action="email.sent", entity_id=first.id, at=datetime(2025, 1, 1), details={}
            )
        )
        db.add(
            Job(kind="send", target_id=newer.id, dedupe_key="scheduled", available_at=datetime(2099, 1, 1))
        )
        db.add(
            Message(
                case_id=case,
                external_id="agent-reply",
                sender="supplier@example.com",
                body="Reply",
                requested_fields=["F1"],
                status="evaluated",
            )
        )
    summaries = client.get("/agents", headers=REVIEW).json()
    assert [s["name"] for s in summaries] == ["Email agent", "Reply evaluation agent"]
    assert summaries[0]["total"] == 2 and summaries[0]["completed"] == 1 and summaries[0]["suppliers"] == 1
    assert summaries[1]["total"] == 1 and summaries[1]["completed"] == 1
    history = client.get("/agents/email/activity", headers=REVIEW).json()
    assert (
        history["items"][0]["id"] == initial["id"]
    )  # Actual send beats creation time, never future scheduling.
    assert history["items"][0]["supplier_name"] == "Fictional Example Ltd"
    assert history["items"][0]["case_id"] == case
    assert client.get("/agents", headers=AUTOMATION).status_code == 403
    assert client.get("/agents/unknown/activity", headers=REVIEW).status_code == 404
    assert client.get("/agents/email/activity?limit=101", headers=REVIEW).status_code == 422


def test_history_pagination_exposes_all_supplier_work(env):
    client, factory, _ = env
    case = seed(client)
    with factory.begin() as db:
        for i in range(53):
            db.add(
                Draft(
                    case_id=case,
                    kind="request",
                    recipient="supplier@example.com",
                    subject="Request",
                    body="Request",
                    requested_fields=["F1"],
                    case_revision=1,
                    created_at=datetime(2020, 1, 1) + timedelta(seconds=i),
                )
            )
    first = client.get("/agents/email/activity?limit=50", headers=REVIEW).json()
    second = client.get("/agents/email/activity?offset=50&limit=50", headers=REVIEW).json()
    assert first["total"] == 53 and len(first["items"]) == 50 and len(second["items"]) == 3
    assert not {p["id"] for p in first["items"]} & {p["id"] for p in second["items"]}
    assert first["items"][-1]["last_touched_at"] > second["items"][0]["last_touched_at"]
