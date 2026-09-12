import csv
import io
import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from nova.config import Settings
from nova.models import Draft, Job, Message, SupplierField, now
from nova.providers import Anymize, FixtureEvaluator, ProviderUnavailable, providers
from nova.schemas import Evaluation
from nova.worker import run_once
from nova.workflow import V2_COLUMNS
from tests.conftest import REVIEW, approve_email, fixture_csv, reply, request_draft, seed


def test_anymize_exposes_only_sanitized_text(monkeypatch):
    settings = Settings(_env_file=None, anymize_api_key="fake-key", anymize_poll_seconds=0)
    calls = []

    def request(method, url, **kwargs):
        calls.append(url)
        if method == "POST":
            return httpx.Response(202, json={"job_id": "job-123"})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "anonymized_text_raw": "[[Organization-123]]",
                "original_text": "SECRET COMPANY",
                "metadata": {"filename": "SECRET.pdf"},
            },
        )

    monkeypatch.setattr(httpx, "request", request)
    assert Anymize(settings).text("SECRET COMPANY") == "[[Organization-123]]"
    assert len(calls) == 2


def test_remote_ai_cannot_use_fixture_anonymization():
    with pytest.raises(ProviderUnavailable):
        providers(Settings(_env_file=None, ai_mode="gemini", anonymizer_mode="fixture"))


def test_supplier_identity_and_original_row_ids_do_not_reach_evaluator(env, monkeypatch):
    client, factory, settings = env
    case = seed(client)
    approve_email(client, request_draft(client, case))
    run_once(factory, settings)
    reply(
        client, case, "F1=Confirmed by Fictional Example Ltd for DEMO-ARTICLE, contact supplier@example.com"
    )
    original = FixtureEvaluator.evaluate
    captured = []

    def inspect_evaluation(self, fields, sources):
        captured.append(json.dumps({"fields": fields, "sources": sources}))
        return original(self, fields, sources)

    monkeypatch.setattr(FixtureEvaluator, "evaluate", inspect_evaluation)
    run_once(factory, settings)
    assert captured
    for identifier in [
        "Fictional Example Ltd",
        "DEMO-ARTICLE",
        "supplier@example.com",
        "SYNTHETIC-001",
        '"F1"',
    ]:
        assert identifier not in captured[0]
    proposal = client.get("/proposals", headers=REVIEW).json()[0]
    assert proposal["field_id"] == "F1"
    assert "Fictional Example Ltd" in proposal["value"]  # restored only in trusted review backend


def test_unverifiable_evidence_blocks_all_proposals(env, monkeypatch):
    client, factory, settings = env
    case = seed(client)
    approve_email(client, request_draft(client, case))
    run_once(factory, settings)
    reply(client, case)

    def fabricated(self, fields, sources):
        return Evaluation(
            candidates=[
                {
                    "field_id": fields[0]["field_id"],
                    "value": "Fabricated",
                    "evidence": {"source_id": "email", "quote": "Not present in email"},
                    "rationale": "Invalid fixture",
                }
            ]
        )

    monkeypatch.setattr(FixtureEvaluator, "evaluate", fabricated)
    run_once(factory, settings)
    assert client.get("/proposals", headers=REVIEW).json() == []
    assert client.get("/jobs", headers=REVIEW).json()[0]["status"] == "failed"


def test_rejection_keeps_original_value(env):
    client, factory, settings = env
    case = seed(client)
    approve_email(client, request_draft(client, case))
    run_once(factory, settings)
    reply(client, case)
    run_once(factory, settings)
    proposal = client.get("/proposals", headers=REVIEW).json()[0]
    assert (
        client.post(f"/proposals/{proposal['id']}/reject", headers=REVIEW, json={"version": 1}).status_code
        == 200
    )
    assert (
        client.post(f"/proposals/{proposal['id']}/approve", headers=REVIEW, json={"version": 1}).status_code
        == 409
    )
    with factory() as db:
        assert db.get(SupplierField, "F1").data["Value submitted"] == ""


def test_digest_protects_against_changed_approved_content(env):
    client, factory, settings = env
    case = seed(client)
    draft = request_draft(client, case)
    approve_email(client, draft)
    with factory.begin() as db:
        db.get(Draft, draft["id"]).body = "Unapproved content"
    run_once(factory, settings)
    assert client.get("/drafts", headers=REVIEW).json()[0]["status"] == "superseded"


def test_old_job_does_not_cancel_a_newer_approved_email_version(env):
    client, factory, settings = env
    case = seed(client)
    draft = request_draft(client, case)
    approve_email(client, draft)
    edited = client.patch(
        f"/drafts/{draft['id']}",
        headers=REVIEW,
        json={"version": 1, "subject": "Reviewed revision", "body": "Updated reviewed request"},
    ).json()
    approve_email(client, edited)
    assert run_once(factory, settings)
    assert client.get("/drafts", headers=REVIEW).json()[0]["status"] == "approved"
    assert run_once(factory, settings)
    assert client.get("/drafts", headers=REVIEW).json()[0]["status"] == "simulated"


def test_restarted_worker_recovers_expired_evaluation(env):
    client, factory, settings = env
    case = seed(client)
    approve_email(client, request_draft(client, case))
    run_once(factory, settings)
    message = reply(client, case)
    with factory.begin() as db:
        job = db.scalar(select(Job).where(Job.kind == "evaluate"))
        job.status, job.lease_until = "running", now() - timedelta(minutes=1)
        job.claim_token = "dead-worker"
        db.get(Message, message["id"]).status = "processing"
    assert run_once(factory, settings)
    assert len(client.get("/proposals", headers=REVIEW).json()) == 1


def test_v2_columns_survive_import_and_export(env):
    client, factory, settings = env
    original = list(csv.DictReader(io.StringIO(fixture_csv())))
    for row in original:
        row.update({"Country": "DE", "Workflow status": "Open", "Last contact date": "2026-09-01"})
    content = io.StringIO()
    writer = csv.DictWriter(content, fieldnames=V2_COLUMNS)
    writer.writeheader()
    writer.writerows(original)
    imported = client.post("/imports", headers=REVIEW, files={"file": ("v2.csv", content.getvalue())}).json()
    assert client.post(f"/imports/{imported['id']}/approve", headers=REVIEW, json={}).status_code == 200
    exported = csv.DictReader(io.StringIO(client.get("/exports/submissions.csv", headers=REVIEW).text))
    assert exported.fieldnames == V2_COLUMNS
    assert list(exported) == original
