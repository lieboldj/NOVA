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


def test_demo100_all_articles_have_scoped_reply_fixtures():
    from nova.demo_replies import demo100_answers

    settings = SimpleNamespace(demo_auto_reply=True, mail_mode="gmail", gmail_supplier=DEMO_MAILBOX)
    fixtures = demo100_answers()
    assert len(fixtures) == 300
    for nart, fields in fixtures.items():
        case = SimpleNamespace(
            supplier_id=nart[:11], nart=nart, supplier_name="Demo Fictional", recipient=DEMO_MAILBOX
        )
        assert enabled_for(settings, case)
        assert fields and all(key.startswith(nart + "-F") for key in fields)
    for sid, nart in [
        ("DEMO100-101", "DEMO100-101-A01"),
        ("DEMO100-001", "DEMO100-001-A04"),
        ("DEMO100-001", "DEMO100-002-A01"),
    ]:
        assert not enabled_for(
            settings,
            SimpleNamespace(
                supplier_id=sid, nart=nart, supplier_name="Demo Fictional", recipient=DEMO_MAILBOX
            ),
        )
    case.supplier_id, case.nart = "DEMO100-100", "DEMO100-100-A03"
    case.recipient = "real-supplier@example.com"
    assert not enabled_for(settings, case)


def test_demo100_formats_partial_and_invalid_answers():
    formats = set()
    for number in (1, 2, 3, 4, 5, 20):
        sid = f"DEMO100-{number:03d}"
        nart = sid + "-A01"
        requested = [nart + "-F01", nart + "-F17", nart + "-F19"]
        body, attachments, mode = response_content(sid, requested_fields=requested, nart=nart)
        assert "DEMO100 scenario" in body
        formats.add(mode)
        text = body
        for name, content in attachments:
            if name.endswith(".pdf"):
                pages = PdfReader(io.BytesIO(content)).pages
                assert pages
                text += "\n".join(page.extract_text() for page in pages)
            else:
                text += content.decode()
        if number == 5:
            assert "2028-13-40" in text
        # Follow-up fixture answers every requested field, without deliberately invalid values.
        body, attachments, _ = response_content(sid, requested_fields=requested, followup=True, nart=nart)
        text = body + "".join(
            content.decode()
            if name.endswith(".txt")
            else "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)
            for name, content in attachments
        )
        assert "2028-13-40" not in text and "unknown" not in text
    assert len(formats) == 6
    sid, nart = "DEMO100-010", "DEMO100-010-A01"
    requested = [nart + f"-F{i:02d}" for i in (1, 2, 3)]
    body, attachments, _ = response_content(sid, requested_fields=requested, nart=nart)
    text = body + "\n".join(
        p.extract_text() for _, content in attachments for p in PdfReader(io.BytesIO(content)).pages
    )
    assert requested[2] not in text


def test_demo100_manual_send_then_simulated_reply_and_extraction(env, monkeypatch):
    import csv
    from pathlib import Path

    from nova.workflow import V2_COLUMNS

    client, factory, settings = env
    settings.mail_mode, settings.gmail_supplier = "gmail", DEMO_MAILBOX
    settings.demo_auto_reply, settings.demo_reply_delay_seconds = True, 0
    settings.auto_send_followups = False
    nart = "DEMO100-001-A01"
    with Path("examples/colleague-demo/demo100/suppliers.csv").open() as stream:
        rows = [r for r in csv.DictReader(stream) if r["NART"] == nart]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=V2_COLUMNS + ["Region", "Industry"])
    writer.writeheader()
    writer.writerows(rows)
    batch = client.post("/imports", headers=REVIEW, files={"file": ("demo100.csv", stream.getvalue())}).json()
    imported = client.post(
        f"/imports/{batch['id']}/approve", headers=REVIEW, json={"contacts": {"DEMO100-001": DEMO_MAILBOX}}
    )
    assert imported.status_code == 200
    case_id = imported.json()["case_ids"][0]
    sent = []
    monkeypatch.setattr(
        "nova.worker.send_email", lambda settings, draft: sent.append(draft.id) or "mock-gmail-demo100"
    )
    draft = request_draft(client, case_id)
    assert draft["status"] == "pending"
    assert not run_once(factory, settings) and not sent
    approve_email(client, draft)
    assert run_once(factory, settings) and sent == [draft["id"]]
    assert run_once(factory, settings)  # internal simulated reply
    assert run_once(factory, settings)  # offline extraction
    assert not run_once(factory, settings)
    messages = client.get(f"/cases/{case_id}/messages", headers=REVIEW).json()
    assert len(messages) == 1 and messages[0]["status"] == "evaluated"
    assert "DEMO100 scenario" in messages[0]["body"]
    proposals = client.get(f"/proposals?case_id={case_id}", headers=REVIEW).json()
    assert len(proposals) == 1 and proposals[0]["field_id"] == nart + "-F01"
    assert proposals[0]["status"] == "pending"
    assert proposals[0]["value"] == "Drawing DEMO-A revision 3"
