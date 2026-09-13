from unittest.mock import patch

import pytest
from sqlalchemy import select

from nova.api import finish_review
from nova.models import Audit, Message, Proposal, SupplierField
from nova.worker import run_once
from tests.conftest import AUTOMATION, REVIEW, approve_email, reply, request_draft, seed


def setup(env, body="F1=Recyled material\nF2=2028-13-40\nF3=Renewable energy"):
    client, factory, settings = env
    case_id = seed(client)
    approve_email(client, request_draft(client, case_id))
    run_once(factory, settings)
    message = reply(client, case_id, body)
    run_once(factory, settings)
    proposals = client.get("/proposals", headers=REVIEW).json()
    entries = [
        {"proposal_id": p["id"], "value": p["value"], "action": "approve", "version": p["version"]}
        for p in proposals
    ]
    return case_id, message, proposals, entries


def test_invalid_batch_rolls_back_then_edits_and_rejections_commit_once(env):
    client, factory, _ = env
    case_id, message, proposals, entries = setup(env)
    endpoint = f"/messages/{message['id']}/approve-all"
    assert client.post(endpoint, headers=AUTOMATION, json=entries).status_code == 403
    next(entry for p, entry in zip(proposals, entries) if p["field_id"] == "F1")["value"] = (
        "Recycled material"
    )
    with patch("nova.api.finish_review", wraps=finish_review) as finish:
        response = client.post(endpoint, headers=REVIEW, json=entries)
        assert response.status_code == 422, response.text
        finish.assert_not_called()
    with factory() as db:
        assert all(
            f.revision == 1 and f.data["Value submitted"] == "" for f in db.scalars(select(SupplierField))
        )
        assert all(p.status == "pending" and p.version == 1 for p in db.scalars(select(Proposal)))
        assert not db.scalar(select(Audit).where(Audit.action == "change.approved"))
        assert db.get(Message, message["id"]).status == "evaluated"
    for p, entry in zip(proposals, entries):
        if p["field_id"] == "F2":
            entry["value"] = "2028-12-31"
        if p["field_id"] == "F3":
            entry.update(action="reject", value="")  # Invalid answers can be rejected.
    with patch("nova.api.finish_review", wraps=finish_review) as finish:
        response = client.post(endpoint, headers=REVIEW, json=entries)
        assert response.status_code == 200, response.text
        finish.assert_called_once()
    with factory() as db:
        assert db.get(SupplierField, "F1").data["Value submitted"] == "Recycled material"
        assert db.get(SupplierField, "F2").data["Value submitted"] == "2028-12-31"
        assert db.get(SupplierField, "F3").data["Value submitted"] == ""
        assert db.get(Message, message["id"]).status == "reviewed"
        events = db.scalars(
            select(Audit).where(Audit.action.in_(["change.approved", "change.rejected"]))
        ).all()
        assert len(events) == 3 and all(e.actor == "local-reviewer" and e.details["field_id"] for e in events)
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["status"] == "open"
    assert client.post(endpoint, headers=REVIEW, json=entries).status_code == 409


@pytest.mark.parametrize(
    "failure", ["duplicate", "missing", "foreign", "version", "field_revision", "options", "document"]
)
def test_batch_rejects_invalid_membership_staleness_and_field_validation(env, failure):
    client, factory, _ = env
    _, message, proposals, entries = setup(env, "F1=Confirmed\nF2=2028-12-31\nF3=Confirmed")
    if failure == "duplicate":
        entries.append(entries[0])
    elif failure == "missing":
        entries.pop()
    elif failure == "foreign":
        entries[0]["proposal_id"] = "another-reply-proposal"
    elif failure == "version":
        client.patch(
            f"/proposals/{proposals[0]['id']}", headers=REVIEW, json={"version": 1, "value": "New version"}
        )
    else:
        with factory.begin() as db:
            field = db.get(SupplierField, proposals[-1]["field_id"])
            if failure == "field_revision":
                field.revision += 1
            elif failure == "options":
                field.rules = {"options": ["Allowed option"]}
            else:
                field.data = field.data | {"Field Type": "File upload"}
                entries[-1]["value"] = "document://not-attached-to-this-reply"
    response = client.post(f"/messages/{message['id']}/approve-all", headers=REVIEW, json=entries)
    assert response.status_code == (422 if failure in ("options", "document") else 409), response.text
    with factory() as db:
        assert all(p.status == "pending" for p in db.scalars(select(Proposal)))
        assert all(f.data["Value submitted"] == "" for f in db.scalars(select(SupplierField)))


def test_complete_reply_closes_case_and_empty_reply_is_independent(env):
    client, factory, settings = env
    case_id, message, _, entries = setup(env, "F1=Confirmed\nF2=2028-12-31\nF3=Confirmed")
    second = reply(client, case_id, "Additional packaging note", external_id="second")
    run_once(factory, settings)
    # The documented minimal entry shape is accepted; UI adds version for stale-edit protection.
    for entry in entries:
        entry.pop("version")
    assert (
        client.post(f"/messages/{message['id']}/approve-all", headers=REVIEW, json=entries).status_code == 200
    )
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["status"] == "data_review"
    assert client.post(f"/messages/{second['id']}/approve-all", headers=REVIEW, json=[]).status_code == 200
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["status"] == "closed"
