import csv
import io
import os

import pytest
from fastapi.testclient import TestClient

from nova.api import create_app
from nova.config import Settings
from nova.db import initialize, make_engine
from nova.models import Base
from nova.workflow import CSV_COLUMNS


@pytest.fixture
def env(tmp_path):
    test_url = os.environ.get("NOVA_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    if test_url.startswith("postgresql"):
        assert test_url.endswith("/nova_test"), "Integration tests require a dedicated nova_test database"
    settings = Settings(
        _env_file=None,
        database_url=test_url,
        storage_path=tmp_path / "documents",
        nova_reviewer_token="review-secret",
        nova_automation_token="automation-secret",
        ai_mode="fixture",
        anonymizer_mode="fixture",
        mail_mode="simulation",
        auto_send_followups=False,
    )
    engine = make_engine(settings.database_url)
    if test_url.startswith("postgresql"):
        Base.metadata.drop_all(engine)
    initialize(engine)
    app = create_app(settings, engine)
    with TestClient(app) as client:
        yield client, app.state.factory, settings
    engine.dispose()


REVIEW = {"Authorization": "Bearer review-secret"}
AUTOMATION = {"Authorization": "Bearer automation-secret"}


def fixture_csv():
    rows = []
    for field_id, label, field_type in [
        ("F1", "Material statement", "Freetext"),
        ("F2", "Certificate valid until", "Date"),
        ("F3", "Energy statement", "Freetext"),
    ]:
        row = dict.fromkeys(CSV_COLUMNS, "")
        row.update(
            {
                "Row ID": field_id,
                "Supplier ID": "SYNTHETIC-001",
                "Supplier Name": "Fictional Example Ltd",
                "NART": "DEMO-ARTICLE",
                "Use case": "MDF",
                "Module (ID)": "1",
                "Section": "Demo",
                "Field (label)": label,
                "Field Type": field_type,
                "Required @ go-live": "Yes",
                "Editable by supplier": "yes",
                "Status": "Missing",
            }
        )
        rows.append(row)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def seed(client):
    response = client.post("/imports", headers=REVIEW, files={"file": ("fixture.csv", fixture_csv())})
    assert response.status_code == 201, response.text
    batch_id = response.json()["id"]
    response = client.post(
        f"/imports/{batch_id}/approve",
        headers=REVIEW,
        json={"contacts": {"SYNTHETIC-001": "supplier@example.com"}},
    )
    assert response.status_code == 200, response.text
    return response.json()["case_ids"][0]


def request_draft(client, case_id):
    response = client.post(f"/cases/{case_id}/draft", headers=REVIEW)
    assert response.status_code == 200, response.text
    return response.json()


def approve_email(client, draft):
    response = client.post(
        f"/drafts/{draft['id']}/approve", headers=REVIEW, json={"version": draft["version"]}
    )
    assert response.status_code == 200, response.text
    return response.json()


def reply(client, case_id, body="F1=Confirmed composition", external_id="reply-001", attachments=None):
    response = client.post(
        f"/cases/{case_id}/messages",
        headers=AUTOMATION,
        data={"external_id": external_id, "sender": "supplier@example.com", "body": body},
        files=attachments,
    )
    assert response.status_code == 201, response.text
    return response.json()
