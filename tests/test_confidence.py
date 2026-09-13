from types import SimpleNamespace

import pytest
from sqlalchemy import select

from nova.confidence import assess
from nova.models import Audit, Draft, Message, Proposal, SupplierField
from nova.review_policy import refresh
from nova.worker import run_once
from tests.conftest import REVIEW, approve_email, reply, request_draft, seed


def prepare(env, body):
    client, factory, settings = env
    settings.auto_accept_high_confidence = True
    case = seed(client)
    approve_email(client, request_draft(client, case))
    run_once(factory, settings)
    message = reply(client, case, body)
    run_once(factory, settings)
    return case, message


def test_clear_complete_reply_is_accepted_and_closed_without_human_approval(env):
    client, factory, _ = env
    case, message = prepare(env, "F1=Recycled aluminium\nF2=2028-12-31\nF3=Renewable energy")
    proposals = client.get("/proposals", headers=REVIEW).json()
    assert len(proposals) == 3
    assert all(
        p["confidence"] == 0.97 and p["automatically_accepted"] and p["status"] == "approved"
        for p in proposals
    )
    assert all(p["confidence_reason"] for p in proposals)
    assert client.get(f"/cases/{case}", headers=REVIEW).json()["status"] == "closed"
    with factory() as db:
        assert db.get(Message, message["id"]).status == "reviewed"
        assert db.get(SupplierField, "F1").data["Value submitted"] == "Recycled aluminium"
        assert len(db.scalars(select(Audit).where(Audit.action == "change.auto_approved")).all()) == 3


def test_missing_invalid_and_unaccounted_inputs_stay_for_review(env):
    client, factory, _ = env
    case, message = prepare(env, "F1=Recycled aluminium\nF2=2028-13-40\nPlease call us about packaging.")
    proposals = {p["field_id"]: p for p in client.get("/proposals", headers=REVIEW).json()}
    assert proposals["F1"]["status"] == "approved"
    assert proposals["F2"]["status"] == "pending" and proposals["F2"]["confidence"] == 0.25
    messages = client.get(f"/cases/{case}/messages", headers=REVIEW).json()
    assert messages[0]["status"] == "evaluated"
    assert messages[0]["missing_data_points"][0]["field_id"] == "F3"
    assert messages[0]["missing_data_points"][0]["confidence"] == 0
    with factory() as db:
        assert db.get(SupplierField, "F2").data["Value submitted"] == ""


@pytest.mark.parametrize(
    "model,mapping,value,quote,expected",
    [
        (0.90, 0.99, "Confirmed", "F1=Confirmed", 0.90),
        (0.99, 0.80, "Confirmed", "Confirmed", 0.80),
        (0.96, 0.95, "Confirmed", "Confirmed", 0.95),
        (None, None, "Confirmed", "Confirmed", 0.65),
        (0.99, 0.99, "unknown", "F1=unknown", 0.0),
        (0.99, 0.99, "Maybe recycled", "F1=Maybe recycled", 0.60),
    ],
)
def test_confidence_rubric_and_strict_threshold(model, mapping, value, quote, expected):
    field = SimpleNamespace(
        id="F1",
        revision=1,
        data={"Field (label)": "Material", "Field Type": "Freetext", "Editable by supplier": "yes"},
        rules={},
    )
    proposal = SimpleNamespace(
        value=value,
        field_revision=1,
        validation_errors=[],
        evidence={"confidence": model, "mapping_confidence": mapping, "quote": quote, "source_id": "email"},
    )
    score, reason = assess(field, proposal)
    assert score == expected and reason


def test_existing_pending_scores_and_templates_refresh_idempotently(env):
    client, factory, settings = env
    case = seed(client)
    draft = request_draft(client, case)
    with factory.begin() as db:
        old = db.get(Draft, draft["id"])
        old.subject = f"[NOVA:{case}] Information request"
        old.body = "Hello Demo Supplier,\n\nPlease reply.\nSupplier Information Team"
    result = refresh(factory, settings)
    assert result["email_templates_updated"] == 1
    assert refresh(factory, settings)["email_templates_updated"] == 0
    updated = client.get("/drafts", headers=REVIEW).json()[0]
    assert updated["subject"] == "Your business partner has an information request"
    assert updated["body"].startswith("Let us stay compliant together.\n\nHello Supplier,")
    assert updated["status"] == "pending" and updated["version"] == 2
    approve_email(client, updated)
    run_once(factory, settings)
    message = reply(client, case, "F1=Recycled aluminium")
    run_once(factory, settings)
    with factory.begin() as db:
        p = db.scalar(select(Proposal))
        p.evidence = {key: value for key, value in p.evidence.items() if "confidence" not in key}
    settings.auto_accept_high_confidence = True
    assert refresh(factory, settings)["automatically_accepted"] == 1
    assert refresh(factory, settings)["scored"] == 0
    with factory() as db:
        assert db.get(Message, message["id"]).status == "evaluated"  # Original inputs remain reviewable.


def test_stale_and_conflicting_answers_are_not_automatically_applied(env):
    client, factory, settings = env
    case = seed(client)
    approve_email(client, request_draft(client, case))
    run_once(factory, settings)
    first = reply(client, case, "F1=First composition")
    run_once(factory, settings)
    second = reply(client, case, "F1=Different composition", external_id="other")
    settings.auto_accept_high_confidence = True
    run_once(factory, settings)
    proposals = client.get("/proposals", headers=REVIEW).json()
    assert all(p["status"] == "pending" for p in proposals)
    assert next(p for p in proposals if p["message_id"] == second["id"])["confidence"] == 0.45
    with factory.begin() as db:
        field = db.get(SupplierField, "F1")
        field.revision += 1
        p = db.scalar(select(Proposal).where(Proposal.message_id == first["id"]))
        p.evidence = p.evidence | {"confidence_policy": "old"}
    assert refresh(factory, settings)["automatically_accepted"] == 0


def test_exactly_ninety_percent_requires_human_acceptance(env, monkeypatch):
    from nova.providers import FixtureEvaluator

    original = FixtureEvaluator.evaluate

    def extract(self, fields, sources):
        result = original(self, fields, sources)
        for candidate in result.candidates:
            candidate.confidence = 0.9
        return result

    monkeypatch.setattr(FixtureEvaluator, "evaluate", extract)
    client, factory, _ = env
    prepare(env, "F1=Recycled aluminium\nF2=2028-12-31\nF3=Renewable energy")
    assert all(
        p["status"] == "pending" and p["confidence"] == 0.9
        for p in client.get("/proposals", headers=REVIEW).json()
    )
    with factory() as db:
        assert all(f.data["Value submitted"] == "" for f in db.scalars(select(SupplierField)))
