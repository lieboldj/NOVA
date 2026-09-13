import csv
import io
from datetime import timedelta

import pytest
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select

from nova.models import Case, Draft, Message, Proposal, SupplierField, now
from nova.worker import run_once
from tests.conftest import AUTOMATION, REVIEW, approve_email, fixture_csv, reply, request_draft, seed


def test_import_is_staged_and_requires_reviewer(env):
    client, factory, _ = env
    response = client.post("/imports", headers=REVIEW, files={"file": ("fixture.csv", fixture_csv())})
    assert response.status_code == 201
    batch = response.json()["id"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SupplierField)) == 0
    assert client.post(f"/imports/{batch}/approve", headers=AUTOMATION, json={}).status_code == 403
    assert client.get("/cases", headers=AUTOMATION).status_code == 403
    assert client.get("/cases").status_code == 401
    assert client.post(f"/imports/{batch}/approve", headers=REVIEW, json={}).status_code == 200
    assert client.post(f"/imports/{batch}/approve", headers=REVIEW, json={}).status_code == 200
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SupplierField)) == 3


def test_no_send_before_approval_and_repeated_triggers_are_safe(env):
    client, factory, settings = env
    case_id = seed(client)
    assert client.post("/automation/tick", headers=AUTOMATION).json()["drafted"] == 1
    assert client.post("/automation/tick", headers=AUTOMATION).json()["drafted"] == 0
    draft = client.get("/drafts", headers=REVIEW).json()[0]
    assert not run_once(factory, settings)
    assert (
        client.post(f"/drafts/{draft['id']}/approve", headers=AUTOMATION, json={"version": 1}).status_code
        == 403
    )
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["last_sent_at"] is None
    approve_email(client, draft)
    approve_email(client, draft)
    assert run_once(factory, settings)
    assert not run_once(factory, settings)
    sent = client.get("/drafts", headers=REVIEW).json()[0]
    assert sent["status"] == "simulated"
    assert sent["approved_by"] == "local-reviewer"
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["next_action_at"] is not None


def test_edit_invalidates_approval_and_old_send_job(env):
    client, factory, settings = env
    case_id = seed(client)
    draft = request_draft(client, case_id)
    approve_email(client, draft)
    edited = client.patch(
        f"/drafts/{draft['id']}",
        headers=REVIEW,
        json={"version": 1, "subject": "Updated request", "body": "Please confirm."},
    ).json()
    assert edited["version"] == 2 and edited["status"] == "pending"
    assert edited["approved_digest"] is None
    assert (
        client.post(f"/drafts/{draft['id']}/approve", headers=REVIEW, json={"version": 1}).status_code == 409
    )
    assert run_once(factory, settings)  # old send cancelled
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["last_sent_at"] is None
    approve_email(client, edited)
    assert run_once(factory, settings)
    assert client.get("/drafts", headers=REVIEW).json()[0]["status"] == "simulated"


def test_pdf_partial_reply_approval_followup_and_export(env):
    client, factory, settings = env
    case_id = seed(client)
    approve_email(client, request_draft(client, case_id))
    run_once(factory, settings)
    pdf = io.BytesIO()
    canvas = Canvas(pdf)
    canvas.drawString(50, 750, "F2=2028-12-31")
    canvas.save()
    message = reply(
        client, case_id, attachments=[("attachments", ("certificate.pdf", pdf.getvalue(), "application/pdf"))]
    )
    assert run_once(factory, settings)
    proposals = client.get("/proposals", headers=REVIEW).json()
    assert len(proposals) == 2
    with factory() as db:
        assert db.get(SupplierField, "F1").data["Value submitted"] == ""
        assert db.get(SupplierField, "F2").data["Status"] == "Missing"
    assert client.post("/automation/tick", headers=AUTOMATION).json()["drafted"] == 0
    for proposal in proposals:
        if proposal["field_id"] == "F2":
            assert proposal["evidence"]["page"] == 1
            doc_id = proposal["evidence"]["document_id"]
            assert client.get(f"/documents/{doc_id}", headers=REVIEW).content == pdf.getvalue()
        assert (
            client.post(
                f"/proposals/{proposal['id']}/approve", headers=AUTOMATION, json={"version": 1}
            ).status_code
            == 403
        )
        response = client.post(f"/proposals/{proposal['id']}/approve", headers=REVIEW, json={"version": 1})
        assert response.status_code == 200, response.text
    assert client.post("/automation/tick", headers=AUTOMATION).json()["drafted"] == 0
    assert client.post(f"/messages/{message['id']}/review-complete", headers=REVIEW).status_code == 200
    assert client.post("/automation/tick", headers=AUTOMATION).json()["drafted"] == 1
    followup = client.get("/drafts", headers=REVIEW).json()[0]
    assert followup["kind"] == "followup" and followup["requested_fields"] == ["F3"]
    assert followup["status"] == "pending"
    exported = list(csv.DictReader(io.StringIO(client.get("/exports/submissions.csv", headers=REVIEW).text)))
    assert exported[0]["Value submitted"] == "Confirmed composition"
    assert exported[1]["Value submitted"] == "2028-12-31"
    assert exported[2]["Status"] == "Missing"
    assert client.get(f"/messages/{message['id']}", headers=REVIEW).json()["status"] == "reviewed"


def test_duplicate_reply_and_arrival_cancels_pending_reminder(env):
    client, factory, settings = env
    case_id = seed(client)
    approve_email(client, request_draft(client, case_id))
    run_once(factory, settings)
    with factory.begin() as db:
        db.get(Case, case_id).next_action_at = now() - timedelta(days=1)
    client.post("/automation/tick", headers=AUTOMATION)
    reminder = client.get("/drafts", headers=REVIEW).json()[0]
    approve_email(client, reminder)
    first = reply(client, case_id)
    second = reply(client, case_id)
    assert second["duplicate"] and first["id"] == second["id"]
    while run_once(factory, settings):
        pass
    with factory() as db:
        assert db.get(Draft, reminder["id"]).status == "superseded"
        assert db.scalar(select(func.count()).select_from(Message)) == 1
        assert db.scalar(select(func.count()).select_from(Proposal)) == 1
        assert db.get(Case, case_id).reminders_sent == 0


def test_reminder_limit_escalates_without_sending(env):
    client, factory, settings = env
    case_id = seed(client)
    approve_email(client, request_draft(client, case_id))
    run_once(factory, settings)
    for _ in range(settings.max_reminders):
        with factory.begin() as db:
            db.get(Case, case_id).next_action_at = now() - timedelta(days=1)
        assert client.post("/automation/tick", headers=AUTOMATION).json()["drafted"] == 1
        draft = client.get("/drafts", headers=REVIEW).json()[0]
        assert draft["kind"] == "reminder" and draft["status"] == "pending"
        assert not run_once(factory, settings)
        approve_email(client, draft)
        run_once(factory, settings)
    with factory.begin() as db:
        db.get(Case, case_id).next_action_at = now() - timedelta(days=1)
    assert client.post("/automation/tick", headers=AUTOMATION).json()["escalated"] == 1
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["status"] == "escalated"


def test_stale_field_proposal_cannot_overwrite_newer_approved_value(env):
    client, factory, settings = env
    case_id = seed(client)
    approve_email(client, request_draft(client, case_id))
    run_once(factory, settings)
    reply(client, case_id, "F1=First confirmation", "first")
    run_once(factory, settings)
    reply(client, case_id, "F1=Second confirmation", "second")
    run_once(factory, settings)
    proposals = client.get("/proposals", headers=REVIEW).json()
    first = next(p for p in proposals if p["value"] == "First confirmation")
    second = next(p for p in proposals if p["value"] == "Second confirmation")
    assert (
        client.post(f"/proposals/{second['id']}/approve", headers=REVIEW, json={"version": 1}).status_code
        == 200
    )
    assert (
        client.post(f"/proposals/{first['id']}/approve", headers=REVIEW, json={"version": 1}).status_code
        == 409
    )
    with factory() as db:
        assert db.get(SupplierField, "F1").data["Value submitted"] == "Second confirmation"


def test_validation_requires_correction_and_fresh_approval(env):
    client, factory, settings = env
    case_id = seed(client)
    approve_email(client, request_draft(client, case_id))
    run_once(factory, settings)
    reply(client, case_id, "F2=not a date")
    run_once(factory, settings)
    proposal = client.get("/proposals", headers=REVIEW).json()[0]
    assert proposal["validation_errors"]
    assert (
        client.post(f"/proposals/{proposal['id']}/approve", headers=REVIEW, json={"version": 1}).status_code
        == 422
    )
    assert (
        client.patch(
            f"/proposals/{proposal['id']}", headers=REVIEW, json={"version": 1, "value": "2028-12-31"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/proposals/{proposal['id']}/reject",
            headers=REVIEW,
            json={"version": 1, "reason": "Please provide a valid date in YYYY-MM-DD format."},
        ).status_code
        == 200
    )
    run_once(factory, settings)
    reply(client, case_id, "F2=2028-12-31", external_id="corrected-date")
    run_once(factory, settings)
    corrected = next(p for p in client.get("/proposals", headers=REVIEW).json() if p["status"] == "pending")
    assert corrected["value"] == "2028-12-31" and not corrected["validation_errors"]
    assert (
        client.post(f"/proposals/{corrected['id']}/approve", headers=REVIEW, json={"version": 1}).status_code
        == 200
    )


def test_missing_anymize_pauses_and_cannot_send_raw_data(env, monkeypatch):
    from pydantic import SecretStr

    from nova.providers import Gemini

    client, factory, settings = env
    case_id = seed(client)
    approve_email(client, request_draft(client, case_id))
    run_once(factory, settings)
    message = reply(client, case_id)
    settings.anonymizer_mode, settings.ai_mode = "anymize", "gemini"
    settings.anymize_api_key = SecretStr("")
    monkeypatch.setattr(Gemini, "evaluate", lambda *args: pytest.fail("Remote model must not be called"))
    run_once(factory, settings)
    assert client.get(f"/messages/{message['id']}", headers=REVIEW).json()["status"] == "failed"
    assert client.get("/proposals", headers=REVIEW).json() == []
    assert client.post("/automation/tick", headers=AUTOMATION).json()["drafted"] == 0
    job = next(j for j in client.get("/jobs", headers=REVIEW).json() if j["kind"] == "evaluate")
    assert "Anymize" in job["error"]
    settings.anonymizer_mode, settings.ai_mode = "fixture", "fixture"
    assert client.post(f"/jobs/{job['id']}/retry", headers=REVIEW).status_code == 200
    run_once(factory, settings)
    assert len(client.get("/proposals", headers=REVIEW).json()) == 1


def test_uncertain_send_is_not_retried(env, monkeypatch):
    client, factory, settings = env
    case_id = seed(client)
    draft = request_draft(client, case_id)
    approve_email(client, draft)

    def ambiguous(*args):
        raise TimeoutError("Provider may have sent before timeout")

    monkeypatch.setattr("nova.worker.send_email", ambiguous)
    run_once(factory, settings)
    assert client.get("/drafts", headers=REVIEW).json()[0]["status"] == "uncertain"
    job = client.get("/jobs", headers=REVIEW).json()[0]
    assert client.post(f"/jobs/{job['id']}/retry", headers=REVIEW).status_code == 409
    assert not run_once(factory, settings)
    assert client.post("/automation/tick", headers=AUTOMATION).json()["drafted"] == 0

    reconciled = client.post(
        f"/drafts/{draft['id']}/reconcile",
        headers=REVIEW,
        json={"version": 1, "outcome": "not_sent", "note": "Confirmed absent in test mailbox"},
    )
    assert reconciled.status_code == 200
    assert reconciled.json()["status"] == "pending"
    assert reconciled.json()["version"] == 2
    assert not run_once(factory, settings)  # a fresh approval is mandatory


def test_full_reply_closes_only_after_approval_and_audits_changes(env):
    client, factory, settings = env
    case_id = seed(client)
    approve_email(client, request_draft(client, case_id))
    run_once(factory, settings)
    message = reply(client, case_id, "F1=Confirmed\nF2=2028-12-31\nF3=Renewable energy confirmed")
    run_once(factory, settings)
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["status"] == "data_review"
    for proposal in client.get("/proposals", headers=REVIEW).json():
        response = client.post(f"/proposals/{proposal['id']}/approve", headers=REVIEW, json={"version": 1})
        assert response.status_code == 200
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["status"] == "data_review"
    assert client.post(f"/messages/{message['id']}/review-complete", headers=REVIEW).status_code == 200
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["status"] == "closed"
    events = client.get("/audit", headers=REVIEW).json()
    assert len([e for e in events if e["action"] == "change.approved"]) == 3


def test_unrelated_reply_needs_human_review_before_followup(env):
    client, factory, settings = env
    case_id = seed(client)
    approve_email(client, request_draft(client, case_id))
    run_once(factory, settings)
    message = reply(client, case_id, "We will get back to you.")
    run_once(factory, settings)
    assert client.get(f"/messages/{message['id']}", headers=REVIEW).json()["status"] == "needs_review"
    assert client.post(f"/cases/{case_id}/draft", headers=REVIEW).status_code == 409
    assert client.post(f"/messages/{message['id']}/review-complete", headers=REVIEW).status_code == 200
    assert client.post("/automation/tick", headers=AUTOMATION).json()["drafted"] == 1


def test_review_includes_unchanged_unsolicited_values_and_all_original_inputs(env):
    client, factory, settings = env
    case_id = seed(client)
    with factory.begin() as db:
        field = db.get(SupplierField, "F1")
        field.data = {**field.data, "Value submitted": "Existing composition", "Status": "Complete"}
    draft = request_draft(client, case_id)
    assert "F1" not in draft["requested_fields"]
    approve_email(client, draft)
    run_once(factory, settings)
    body = "F1=Existing composition\nF2=2028-12-31\nAdditional note: delivery is delayed."
    first = reply(
        client,
        case_id,
        body,
        "all-inputs",
        attachments=[
            ("attachments", ("extra-notes.txt", b"Please call us about packaging.", "text/plain")),
            ("attachments", ("energy.txt", b"F3=Renewable energy confirmed", "text/plain")),
        ],
    )
    run_once(factory, settings)
    proposals = client.get("/proposals", headers=REVIEW).json()
    assert {p["field_id"] for p in proposals} == {"F1", "F2", "F3"}
    unchanged = next(p for p in proposals if p["field_id"] == "F1")
    assert unchanged["old_value"] == unchanged["value"] == "Existing composition"
    assert unchanged["status"] == "pending"
    assert client.post(f"/messages/{first['id']}/review-complete", headers=REVIEW).status_code == 409

    # A second reply with no candidate is still an independent item in the same review.
    second = reply(client, case_id, "We will send more details next week.", "additional-input")
    run_once(factory, settings)
    received = client.get(f"/cases/{case_id}/messages", headers=REVIEW).json()
    assert len(received) == 2
    original = next(m for m in received if m["id"] == first["id"])
    assert original["body"] == body
    assert {d["filename"] for d in original["documents"]} == {"extra-notes.txt", "energy.txt"}
    notes = next(d for d in original["documents"] if d["filename"] == "extra-notes.txt")
    assert (
        client.get(f"/documents/{notes['id']}", headers=REVIEW).content == b"Please call us about packaging."
    )
    assert client.post(f"/messages/{second['id']}/review-complete", headers=AUTOMATION).status_code == 403
    # Decisions are scoped to the reply; another reply's pending proposals do not prevent its review.
    assert client.post(f"/messages/{second['id']}/review-complete", headers=REVIEW).status_code == 200
    for proposal in proposals:
        assert (
            client.post(
                f"/proposals/{proposal['id']}/approve", headers=REVIEW, json={"version": 1}
            ).status_code
            == 200
        )
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["status"] == "data_review"
    assert client.post(f"/cases/{case_id}/draft", headers=REVIEW).status_code == 409
    assert client.post("/automation/tick", headers=AUTOMATION).json()["closed"] == 0
    assert client.post(f"/messages/{first['id']}/review-complete", headers=REVIEW).status_code == 200
    assert client.get(f"/cases/{case_id}", headers=REVIEW).json()["status"] == "closed"
