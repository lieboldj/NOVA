from datetime import timedelta

import pytest
from sqlalchemy import select

from nova.config import Settings
from nova.models import Audit, Case, Draft, Job, now
from nova.worker import run_once
from nova.workflow import AI_DISCLOSURE, create_draft, draft_digest
from tests.conftest import AUTOMATION, REVIEW, approve_email, reply, request_draft, seed


def prepare(env, kind="reminder"):
    client, factory, settings = env
    settings.auto_send_followups = True
    case_id = seed(client)
    initial = request_draft(client, case_id)
    assert initial["status"] == "pending" and initial["approved_by"] is None
    assert not run_once(factory, settings)
    approve_email(client, initial)
    run_once(factory, settings)
    with factory.begin() as db:
        case = db.get(Case, case_id)
        case.next_action_at = now() - timedelta(days=1)
        if kind == "followup":
            case.last_reply_at = now()
    assert client.post("/automation/tick", headers=AUTOMATION).json()["drafted"] == 1
    draft = client.get("/drafts", headers=REVIEW).json()[0]
    assert draft["kind"] == kind
    return case_id, draft


def make_due(factory, draft_id):
    with factory.begin() as db:
        db.scalar(select(Job).where(Job.target_id == draft_id)).available_at = now() - timedelta(seconds=1)


@pytest.mark.parametrize("kind", ["followup", "reminder"])
def test_default_delay_manual_initial_and_idempotent_automation(env, kind):
    client, factory, settings = env
    defaults = Settings(_env_file=None)
    assert defaults.auto_send_followups and defaults.auto_send_delay_minutes == 2
    case_id, draft = prepare(env, kind)
    assert draft["status"] == "approved" and draft["approved_by"] == "automation"
    assert draft["body"].endswith(AI_DISCLOSURE)
    with factory.begin() as db:
        current = db.get(Draft, draft["id"])
        assert current.approved_digest == draft_digest(current)
        job = db.scalar(select(Job).where(Job.target_id == current.id))
        assert timedelta(seconds=115) < job.available_at - now() <= timedelta(minutes=2)
        again = create_draft(db, db.get(Case, case_id), kind, settings=settings)
        assert again.id == current.id
        assert len(db.scalars(select(Audit).where(Audit.action == "email.auto_approved")).all()) == 1
    assert not run_once(factory, settings)
    make_due(factory, draft["id"])
    assert run_once(factory, settings)
    assert not run_once(factory, settings)
    with factory() as db:
        assert db.get(Draft, draft["id"]).status == "simulated"
        assert db.get(Case, case_id).reminders_sent == (1 if kind == "reminder" else 0)


@pytest.mark.parametrize("change", ["edit", "reject", "reply", "digest", "revision", "disable"])
def test_review_window_blocks_obsolete_send(env, change):
    client, factory, settings = env
    case_id, draft = prepare(env)
    if change == "edit":
        response = client.patch(
            f"/drafts/{draft['id']}",
            headers=REVIEW,
            json={"version": 1, "subject": draft["subject"], "body": "Edited reminder"},
        )
        assert response.status_code == 200
        edited = response.json()
        assert edited["version"] == 2 and edited["status"] == "pending"
        assert edited["approved_by"] is None and edited["approved_digest"] is None
    elif change == "reject":
        assert (
            client.post(f"/drafts/{draft['id']}/reject", headers=REVIEW, json={"version": 1}).status_code
            == 200
        )
    elif change == "reply":
        reply(client, case_id)
        run_once(factory, settings)  # evaluation can run during the send delay
    elif change == "disable":
        settings.auto_send_followups = False
    else:
        with factory.begin() as db:
            if change == "digest":
                db.get(Draft, draft["id"]).body = "Unexpected mutation"
            else:
                db.get(Case, case_id).revision += 1
    make_due(factory, draft["id"])
    assert run_once(factory, settings)
    with factory() as db:
        assert db.scalar(select(Job).where(Job.target_id == draft["id"])).status == "cancelled"
        assert db.get(Case, case_id).reminders_sent == 0
        assert db.get(Draft, draft["id"]).status not in ("sent", "simulated")
    if change == "edit":
        approve_email(client, edited)
        assert run_once(factory, settings)
        with factory() as db:
            assert db.get(Draft, draft["id"]).status == "simulated"


def test_incomplete_reply_uses_same_delay(env):
    client, factory, settings = env
    settings.auto_send_followups = settings.auto_followup_enabled = True
    case_id = seed(client)
    approve_email(client, request_draft(client, case_id))
    run_once(factory, settings)
    reply(client, case_id)
    run_once(factory, settings)
    draft = client.get("/drafts", headers=REVIEW).json()[0]
    assert draft["kind"] == "auto_followup" and draft["approved_by"] == "automation"
    assert not run_once(factory, settings)
    make_due(factory, draft["id"])
    assert run_once(factory, settings)
