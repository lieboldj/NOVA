from sqlalchemy import select

from nova.models import Case, Draft, Message, SupplierField
from nova.worker import run_once
from nova.workflow import tick
from scripts.run_demo import seed, supplier_reply
from tests.conftest import REVIEW, approve_email


def test_interactive_demo_waits_for_both_approvals(env):
    client, factory, settings = env
    case_id = seed(factory)
    supplier_reply(factory, settings, case_id)
    with factory() as db:
        assert not db.scalar(select(Message.id))
    draft = client.get("/drafts", headers=REVIEW).json()[0]
    approve_email(client, draft)
    run_once(factory, settings)
    supplier_reply(factory, settings, case_id)
    supplier_reply(factory, settings, case_id)
    run_once(factory, settings)
    proposals = client.get("/proposals", headers=REVIEW).json()
    assert len(proposals) == 1
    first = proposals[0]
    assert first["field_id"] == "DEMO-F1"
    assert first["evidence"]["document_id"]
    with factory() as db:
        assert db.get(SupplierField, "DEMO-F1").data["Value submitted"] == ""
        assert len(db.scalars(select(Message)).all()) == 1
    assert (
        client.post(
            f"/proposals/{first['id']}/approve", headers=REVIEW, json={"version": first["version"]}
        ).status_code
        == 200
    )
    with factory.begin() as db:
        assert tick(db, settings)["drafted"] == 1
        followup = db.scalar(select(Draft).where(Draft.kind == "followup"))
        assert followup.status == "pending"
        assert followup.requested_fields == ["DEMO-F2"]
    assert not run_once(factory, settings)
    approve_email(client, {"id": followup.id, "version": followup.version})
    run_once(factory, settings)
    supplier_reply(factory, settings, case_id)
    run_once(factory, settings)
    final = next(p for p in client.get("/proposals", headers=REVIEW).json() if p["field_id"] == "DEMO-F2")
    assert final["status"] == "pending"
    with factory() as db:
        assert db.get(Case, case_id).status != "closed"
        assert db.get(SupplierField, "DEMO-F2").data["Value submitted"] == ""
    assert (
        client.post(
            f"/proposals/{final['id']}/approve", headers=REVIEW, json={"version": final["version"]}
        ).status_code
        == 200
    )
    with factory() as db:
        assert db.get(Case, case_id).status == "closed"
        assert db.get(SupplierField, "DEMO-F2").data["Value submitted"] == "2027-12-31"
