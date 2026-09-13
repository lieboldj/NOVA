import csv
import io

import pytest
from sqlalchemy import select

from nova.models import Audit, Case, Draft, Job, SupplierField
from nova.worker import run_once
from nova.workflow import CSV_COLUMNS
from tests.conftest import AUTOMATION, REVIEW, approve_email, fixture_csv

COMMAND = "For the suppliers who are in region APAC and are in automotive industry, send the MDF request."


def audience(client):
    source = list(csv.DictReader(io.StringIO(fixture_csv())))[0]
    rows = []
    for sid, region, industry in [
        ("A1", "APAC", "Automotive"),
        ("A2", "apac", "automotive"),
        ("E1", "EMEA", "Automotive"),
        ("T1", "APAC", "Technology"),
        ("U1", "", ""),
    ]:
        for use_case in ["MDF", "PCF"]:
            rows.append(
                source
                | {
                    "Row ID": f"{sid}-{use_case}",
                    "Supplier ID": sid,
                    "Supplier Name": f"Supplier {sid}",
                    "Use case": use_case,
                    "Region": region,
                    "Industry": industry,
                }
            )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS + ["Region", "Industry"])
    writer.writeheader()
    writer.writerows(rows)
    response = client.post("/imports", headers=REVIEW, files={"file": ("audience.csv", output.getvalue())})
    assert response.status_code == 201, response.text
    approved = client.post(
        f"/imports/{response.json()['id']}/approve",
        headers=REVIEW,
        json={"contacts": {sid: f"{sid}@example.com" for sid in ["A1", "A2", "E1", "T1", "U1"]}},
    )
    assert approved.status_code == 200, approved.text


def preview(client, command=COMMAND):
    response = client.post("/processes/preview", headers=REVIEW, json={"command": command})
    assert response.status_code == 200, response.text
    return response.json()


def start(client, result, ids=None):
    return client.post(
        "/processes/start",
        headers=REVIEW,
        json={
            "preview_token": result["preview_token"],
            "case_ids": ids
            if ids is not None
            else [item["id"] for item in result["matches"] if item["eligible"]],
        },
    )


def test_human_batch_targets_intersection_and_requires_email_approval(env):
    client, factory, settings = env
    audience(client)
    result = preview(client)
    assert {item["supplier_id"] for item in result["matches"]} == {"A1", "A2"}
    assert result["supplier_count"] == 2
    assert result["missing_metadata_count"] == 1
    with factory() as db:
        assert not db.scalar(select(Draft))
        assert not db.scalar(select(Job))
    response = start(client, result)
    assert response.status_code == 200, response.text
    assert len(response.json()["drafts"]) == 2
    with factory() as db:
        drafts = db.scalars(select(Draft)).all()
        assert all(d.status == "pending" and d.subject == "Your business partner has an information request" for d in drafts)
        assert {fid for d in drafts for fid in d.requested_fields} == {"A1-MDF", "A2-MDF"}
        assert not db.scalar(select(Job))
        events = db.scalars(select(Audit).where(Audit.action == "process.initiated")).all()
        assert len(events) == 2 and all(event.actor != "automation" for event in events)
        assert events[0].details["command"] == COMMAND
    assert not run_once(factory, settings)
    # Replaying the preview cannot duplicate drafts.
    assert start(client, result).status_code == 409
    draft = client.get("/drafts", headers=REVIEW).json()[0]
    approve_email(client, draft)
    assert run_once(factory, settings)


def test_selection_is_bound_to_preview_and_can_be_narrowed(env):
    client, factory, _ = env
    audience(client)
    result = preview(client)
    excluded = next(c for c in client.get("/cases", headers=REVIEW).json() if c["supplier_id"] == "E1")
    assert start(client, result, [excluded["id"]]).status_code == 422
    assert start(client, result, [result["matches"][0]["id"]]).status_code == 200
    with factory() as db:
        assert len(db.scalars(select(Draft)).all()) == 1


@pytest.mark.parametrize(
    "command",
    [
        "Send MDF to suppliers in APAC or EMEA",
        "Send MDF to all suppliers except automotive",
        "Send MDF to APAC suppliers with revenue above 100",
        "Send MDF to suppliers in Atlantis",
        "Send MDF",
        "Send PCF to all suppliers",
    ],
)
def test_unsupported_or_ambiguous_requests_do_not_broaden_audience(env, command):
    client, factory, _ = env
    audience(client)
    response = client.post("/processes/preview", headers=REVIEW, json={"command": command})
    assert response.status_code == 422
    with factory() as db:
        assert not db.scalar(select(Draft))


def test_named_suppliers_all_and_no_matches(env):
    client, _, _ = env
    audience(client)
    assert preview(client, "Send MDF to Supplier A1 and A2")["supplier_count"] == 2
    assert preview(client, "Send MDF to all suppliers")["supplier_count"] == 5
    assert preview(client, "Send MDF to automotive suppliers in LATAM")["matches"] == []


def test_stale_preview_rolls_back_entire_batch_and_excludes_blocked_cases(env):
    client, factory, _ = env
    audience(client)
    result = preview(client)
    with factory.begin() as db:
        case = db.get(Case, result["matches"][-1]["id"])
        case.recipient = ""
        case.revision += 1
    assert start(client, result).status_code == 409
    with factory() as db:
        assert not db.scalar(select(Draft))
    refreshed = preview(client)
    assert sum(item["eligible"] for item in refreshed["matches"]) == 1
    assert start(client, refreshed).status_code == 200


def test_metadata_round_trip_conflicts_and_reviewer_boundary(env):
    client, factory, _ = env
    audience(client)
    exported = client.get("/exports/submissions.csv", headers=REVIEW)
    assert exported.status_code == 200
    assert list(csv.DictReader(io.StringIO(exported.text)))[0]["Region"] == "APAC"
    with factory.begin() as db:
        field = db.get(SupplierField, "A1-PCF")
        field.data = field.data | {"Region": "EMEA"}
    assert preview(client)["supplier_count"] == 1
    assert client.post("/processes/preview", headers=AUTOMATION, json={"command": COMMAND}).status_code == 403
    result = preview(client)
    assert (
        client.post(
            "/processes/start",
            headers=AUTOMATION,
            json={
                "preview_token": result["preview_token"],
                "case_ids": [result["matches"][0]["id"]],
            },
        ).status_code
        == 403
    )
    result["preview_token"] += "tampered"
    assert start(client, result).status_code == 409
