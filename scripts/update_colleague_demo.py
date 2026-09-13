"""Update only untouched DEMO20 fixtures in one transaction; never send or erase mail."""

import os

from google.cloud import storage
from sqlalchemy import select

from nova.config import get_settings
from nova.db import make_engine, sessions
from nova.models import Case, Draft, Message, SupplierField
from nova.workflow import OUTSTANDING, audit, create_draft, invalidate_drafts, parse_csv


def apply_rows(factory, rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["Supplier ID"], []).append(row)
    expected = {f"DEMO20-{i:02d}" for i in range(1, 21)}
    if set(grouped) != expected:
        raise RuntimeError("Only the complete DEMO20 fixture is supported")
    with factory.begin() as db:
        cases = db.scalars(
            select(Case).where(Case.supplier_id.in_(expected)).order_by(Case.id).with_for_update()
        ).all()
        if len(cases) != 20:
            raise RuntimeError("Expected exactly twenty existing demo cases")
        # Validate the entire scope before modifying any supplier or draft.
        for case in cases:
            if case.nart != case.supplier_id + "-ARTICLE" or not case.supplier_name.startswith("Demo "):
                raise RuntimeError("Unexpected demo identity")
            if case.last_sent_at or case.last_reply_at or case.status not in ("open", "email_review"):
                raise RuntimeError("A demo is already in use; preserve its workflow and inspect it manually")
            if db.scalar(select(Message.id).where(Message.case_id == case.id).limit(1)):
                raise RuntimeError("A demo has supplier replies; update stopped")
            drafts = db.scalars(select(Draft).where(Draft.case_id == case.id)).all()
            if any(d.status not in ("pending", "superseded") for d in drafts):
                raise RuntimeError("A draft has already been acted on; update stopped")
        for case in cases:
            current = {
                f.id: f for f in db.scalars(select(SupplierField).where(SupplierField.case_id == case.id))
            }
            target = {r["Row ID"]: r for r in grouped[case.supplier_id]}
            if not set(current) <= set(target):
                raise RuntimeError("Unexpected existing demo fields; no fields will be deleted")
            changed = False
            for fid, data in target.items():
                if fid not in current:
                    db.add(SupplierField(id=fid, case_id=case.id, data=data, rules={}))
                    changed = True
                elif current[fid].data != data:
                    current[fid].data = data
                    current[fid].revision += 1
                    changed = True
            if changed:
                invalidate_drafts(db, case)
                db.flush()
                draft = create_draft(db, case, "request", use_case="MDF")
                count = sum(r["Status"] in OUTSTANDING for r in target.values())
                if len(draft.requested_fields) != count:
                    raise RuntimeError("Draft and dataset outstanding counts differ")
                audit(
                    db, "demo-setup", "demo.dataset.updated", case.id, fields=len(target), outstanding=count
                )
        print("Committed varied DEMO20 fields and fresh unapproved request drafts.", flush=True)


def main():
    content = (
        storage.Client().bucket(os.environ["DEMO_BUCKET"]).blob(os.environ["DEMO_OBJECT"]).download_as_bytes()
    )
    apply_rows(sessions(make_engine(get_settings().database_url)), parse_csv(content))


if __name__ == "__main__":
    main()
