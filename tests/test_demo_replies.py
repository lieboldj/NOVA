import io
from types import SimpleNamespace

from pypdf import PdfReader
from sqlalchemy import select

from nova.demo_replies import DEMO_MAILBOX, enabled_for, response_content
from nova.models import Case, Draft, Job, Message
from nova.worker import run_once
from tests.conftest import REVIEW, approve_email, request_draft, seed


def test_simulator_is_restricted_and_formats_include_scanned_evidence():
    settings = SimpleNamespace(demo_auto_reply=True, mail_mode="gmail", gmail_supplier=DEMO_MAILBOX)
    case = SimpleNamespace(
        supplier_id="DEMO20-01", nart="DEMO20-01-ARTICLE", supplier_name="Demo Alder", recipient=DEMO_MAILBOX
    )
    assert enabled_for(settings, case)
    case.supplier_id = "REAL-SUPPLIER"
    assert not enabled_for(settings, case)
    formats = set()
    for i in range(1, 21):
        body, attachments, mode = response_content(f"DEMO20-{i:02d}")
        assert body.startswith("SIMULATED SUPPLIER REPLY")
        formats.add(mode)
        for name, content in attachments:
            if name.endswith(".pdf"):
                reader = PdfReader(io.BytesIO(content))
                assert reader.pages
                if mode.startswith("scanned"):
                    assert not reader.pages[0].extract_text().strip()
                else:
                    assert "DEMO20-" in reader.pages[0].extract_text()
    assert len(formats) == 6


def test_approved_real_send_queues_one_labelled_simulation(env, monkeypatch):
    client, factory, settings = env
    case_id = seed(client)
    settings.mail_mode = "gmail"
    settings.gmail_supplier = DEMO_MAILBOX
    settings.demo_auto_reply = True
    settings.demo_reply_delay_seconds = 0
    with factory.begin() as db:
        case = db.get(Case, case_id)
        case.supplier_id, case.nart = "DEMO20-01", "DEMO20-01-ARTICLE"
        case.supplier_name, case.recipient = "Demo Alder", DEMO_MAILBOX
    sent = []
    monkeypatch.setattr(
        "nova.worker.send_email", lambda settings, draft: sent.append(draft.recipient) or "gmail-real-id"
    )
    draft = request_draft(client, case_id)
    assert not run_once(factory, settings)  # no email or response before approval
    approve_email(client, draft)
    assert run_once(factory, settings)
    assert sent == [DEMO_MAILBOX]
    assert run_once(factory, settings)
    messages = client.get("/cases/" + case_id + "/messages", headers=REVIEW).json()
    assert len(messages) == 1
    assert messages[0]["external_id"] == "demo-simulated:" + draft["id"]
    assert messages[0]["body"].startswith("SIMULATED SUPPLIER REPLY")
    with factory.begin() as db:
        job = db.scalar(select(Job).where(Job.kind == "demo_reply"))
        job.status = "queued"
        # Keep evaluation out of this test; run the delivery retry first.
        for evaluation in db.scalars(select(Job).where(Job.kind == "evaluate")):
            evaluation.status = "cancelled"
    assert run_once(factory, settings)
    with factory() as db:
        assert len(db.scalars(select(Message)).all()) == 1
        assert db.get(Draft, draft["id"]).status == "sent"
