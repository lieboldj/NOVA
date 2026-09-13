import json
from collections import Counter
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select

from nova.models import Case, Draft, Job, SupplierField, now
from nova.providers import FixtureEvaluator
from nova.worker import run_once
from nova.workflow import OUTSTANDING, STATUSES, V2_COLUMNS, parse_csv
from tests.conftest import AUTOMATION, REVIEW, approve_email, reply, request_draft


def test_scale_import_and_selected_offline_cadence(env, monkeypatch):
    client, factory, settings = env
    settings.auto_send_followups = True
    content = Path("examples/colleague-demo/demo100/suppliers.csv").read_bytes()
    rows = parse_csv(content)
    assert list(rows[0]) == V2_COLUMNS + ["Region", "Industry"]
    suppliers = {r["Supplier ID"] for r in rows}
    assert len(suppliers) == 100 and all(s.startswith("DEMO100-") for s in suppliers)
    assert len(rows) == 6600 and {r["Status"] for r in rows} == STATUSES
    assert len({r["Country"] for r in rows}) == 20
    assert set(Counter(r["Supplier ID"] for r in rows).values()) == {66}
    workloads = Counter(r["NART"] for r in rows if r["Status"] in OUTSTANDING)
    assert len(workloads) == 300 and set(workloads.values()) == set(range(1, 21))
    imported = client.post("/imports", headers=REVIEW, files={"file": ("demo100.csv", content)})
    assert imported.status_code == 201, imported.text
    with factory() as db:
        assert db.scalar(select(func.count(SupplierField.id))) == 0
    approved = client.post(
        f"/imports/{imported.json()['id']}/approve",
        headers=REVIEW,
        json={"contacts": {"DEMO100-001": "supplier@example.com"}},
    )
    assert approved.status_code == 200, approved.text
    with factory() as db:
        assert db.scalar(select(func.count(Case.id))) == 300
        assert db.scalar(select(func.count(SupplierField.id))) == 6600
        assert db.scalar(select(func.count(Job.id))) == 0
        case_id = db.scalar(select(Case.id).where(Case.nart == "DEMO100-001-A01"))
    initial = request_draft(client, case_id)
    assert initial["status"] == "pending" and len(initial["requested_fields"]) == 1
    approve_email(client, initial)
    assert run_once(factory, settings)
    with factory.begin() as db:
        db.get(Case, case_id).next_action_at = now() - timedelta(days=1)
    client.post("/automation/tick", headers=AUTOMATION)
    reminders = client.get(f"/drafts?case_id={case_id}", headers=REVIEW).json()
    reminder = next(d for d in reminders if d["kind"] == "reminder")
    assert reminder["status"] == "approved"
    assert not run_once(factory, settings)
    with factory.begin() as db:
        db.scalar(select(Job).where(Job.target_id == reminder["id"])).available_at = now() - timedelta(
            seconds=1
        )
    assert run_once(factory, settings)
    original = FixtureEvaluator.evaluate
    captured = []

    def inspect_evaluation(self, fields, sources):
        captured.append(json.dumps({"fields": fields, "sources": sources}))
        return original(self, fields, sources)

    monkeypatch.setattr(FixtureEvaluator, "evaluate", inspect_evaluation)
    message = reply(client, case_id, f"{initial['requested_fields'][0]}=Drawing DEMO100 revision 4")
    assert run_once(factory, settings)
    proposals = client.get(f"/proposals?case_id={case_id}", headers=REVIEW).json()
    assert len(proposals) == 1
    assert captured and "FIELD_0001=" in captured[0]
    assert "DEMO100-001" not in captured[0]
    assert "Demo Alderhaven Motion Works" not in captured[0]
    assert "supplier@example.com" not in captured[0]
    response = client.post(
        f"/messages/{message['id']}/approve-all",
        headers=REVIEW,
        json=[{"proposal_id": p["id"], "value": p["value"], "action": "approve"} for p in proposals],
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["status"] == "closed"
    with factory() as db:
        assert db.scalar(select(func.count(Draft.id)).where(Draft.status == "simulated")) == 2
