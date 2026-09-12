"""Interactive demo using disposable data, simulated delivery, and scripted PDF replies."""

import argparse
import io
import tempfile
import threading
from pathlib import Path

import uvicorn
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select

from nova.api import create_app
from nova.config import Settings
from nova.db import initialize
from nova.inbox import ingest_message
from nova.models import Case, Draft, Message, SupplierField
from nova.worker import run_once
from nova.workflow import CSV_COLUMNS, audit, tick

REVIEW_KEY = "nova-demo"


def seed(factory):
    with factory.begin() as db:
        case = Case(
            supplier_id="DEMO-SUPPLIER",
            supplier_name="Demo Circular Materials",
            nart="NOVA-DEMO-001",
            recipient="supplier@example.com",
        )
        db.add(case)
        db.flush()
        for field_id, label, kind in [
            ("DEMO-F1", "Material composition", "Freetext"),
            ("DEMO-F2", "Certificate valid until", "Date"),
        ]:
            row = dict.fromkeys(CSV_COLUMNS, "")
            row.update(
                {
                    "Row ID": field_id,
                    "Supplier ID": case.supplier_id,
                    "Supplier Name": case.supplier_name,
                    "NART": case.nart,
                    "Use case": "MDF",
                    "Module (ID)": "1",
                    "Section": "Demo evidence",
                    "Field (label)": label,
                    "Field Type": kind,
                    "Required @ go-live": "Yes",
                    "Editable by supplier": "yes",
                    "Status": "Missing",
                }
            )
            db.add(SupplierField(id=field_id, case_id=case.id, data=row, rules={}))
        db.flush()
        audit(db, "demo-setup", "case.fixture_loaded", case.id)
        case.next_action_at = None  # The reviewer initiates this demo through Start process.
        return case.id


def supplier_reply(factory, settings, case_id):
    """Respond only to a draft that the human has approved and the worker has simulated sending."""
    with factory.begin() as db:
        for draft in db.scalars(
            select(Draft)
            .where(Draft.case_id == case_id, Draft.status == "simulated")
            .order_by(Draft.created_at)
        ):
            external_id = f"demo-reply:{draft.id}"
            if db.scalar(select(Message.id).where(Message.external_id == external_id)):
                continue
            first = draft.kind == "request"
            text = "DEMO-F1=80% recycled aluminium" if first else "DEMO-F2=2027-12-31"
            stream = io.BytesIO()
            pdf = Canvas(stream, invariant=1)
            pdf.drawString(50, 780, "Fictional supplier evidence - NOVA demonstration")
            pdf.drawString(50, 750, text)
            pdf.save()
            ingest_message(
                db,
                settings,
                case_id,
                external_id,
                "supplier@example.com",
                "Please find the requested material statement attached. The certificate will follow."
                if first
                else "Please find the remaining certificate information attached.",
                [("material-statement.pdf" if first else "certificate.pdf", stream.getvalue())],
                "demo-supplier",
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8012)
    args = parser.parse_args()
    if not Path("dist/index.html").is_file():
        parser.exit(1, "Build the portal first with npm run build, or use npm run demo.\n")
    with tempfile.TemporaryDirectory(prefix="nova-interactive-demo-") as directory:
        root = Path(directory)
        settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{root / 'demo.db'}",
            storage_path=root / "documents",
            frontend_dist=Path("dist"),
            nova_reviewer_token=REVIEW_KEY,
            nova_automation_token="nova-demo-automation",
            nova_reviewer_name="demo-reviewer",
            nova_cookie_secure=False,
            nova_session_cookie="nova_demo_review",
            ai_mode="fixture",
            anonymizer_mode="fixture",
            mail_mode="simulation",
            gemini_api_key="",
            anymize_api_key="",
            gmail_client_id="",
            gmail_client_secret="",
            gmail_refresh_token="",
            gmail_mailbox="nova@example.com",
            gmail_supplier="supplier@example.com",
            smtp_host="",
            smtp_password="",
        )
        settings.storage_path.mkdir()
        app = create_app(settings)
        initialize(app.state.engine)
        case_id = seed(app.state.factory)
        stopped = threading.Event()

        def worker():
            while not stopped.wait(0.5):
                run_once(app.state.factory, settings)
                supplier_reply(app.state.factory, settings, case_id)
                with app.state.factory.begin() as db:
                    tick(db, settings)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        print(f"\nNOVA interactive demo: http://localhost:{args.port}/", flush=True)
        print(f"Reviewer access key: {REVIEW_KEY}", flush=True)
        print(
            "Fictional data, simulated email, scripted evaluation. No live providers or .env used.",
            flush=True,
        )
        print(
            "Use Start process to prepare a request; review its PDF proposal, follow-up and final value.",
            flush=True,
        )
        print("Restart this command to reset the disposable demo.\n", flush=True)
        try:
            uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
        finally:
            stopped.set()
            thread.join(timeout=10)
            app.state.engine.dispose()


if __name__ == "__main__":
    main()
