"""Human initiation using a bounded, local natural-language command vocabulary."""

import hashlib
import json
import re

from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import Field
from sqlalchemy import select

from nova.models import Case, Draft, SupplierField
from nova.schemas import StrictModel
from nova.workflow import (
    ACTIVE_DRAFTS,
    OUTSTANDING,
    audit,
    blocking_message,
    create_draft,
    fail,
    locked,
    pending_review,
)


class ProcessPreview(StrictModel):
    command: str = Field(min_length=1, max_length=2000)


class ProcessStart(StrictModel):
    preview_token: str = Field(min_length=1, max_length=200000)
    case_ids: list[str] = Field(min_length=1, max_length=500)


def normalized(value):
    return re.sub(r"\s+", " ", value.strip().casefold())


def profile(fields):
    result = {}
    for key in ("Region", "Industry"):
        values = {normalized(f.data.get(key, "")) for f in fields} - {""}
        # Missing attributes never imply membership; conflicting attributes need correction.
        result[key.lower()] = next(iter(values)) if len(values) == 1 else None
    return result


def parse_command(command, cases, fields):
    remaining = normalized(command)
    if not re.search(r"\bmdf\b", remaining):
        fail(
            "Specify the MDF questionnaire, for example: Send the MDF request to APAC automotive suppliers.",
            422,
        )
    remaining = re.sub(r"\bmdf\b", " ", remaining)
    criteria = {"use_case": "MDF", "region": [], "industry": [], "supplier_ids": []}
    vocab = {
        "region": {"apac", "emea", "amer", "latam", "north america", "europe", "asia pacific"},
        "industry": {"automotive"},
    }
    for field in fields:
        for key in vocab:
            value = normalized(field.data.get(key.title(), ""))
            if value:
                vocab[key].add(value)
    # Longest names first so a shorter supplier name cannot consume part of another.
    supplier_names = {}
    for case in cases:
        for value in (case.supplier_id, case.supplier_name):
            supplier_names.setdefault(normalized(value), set()).add(case.supplier_id)
    values = [(value, key, None) for key, items in vocab.items() for value in items]
    values += [(value, "supplier_ids", ids) for value, ids in supplier_names.items()]
    for value, key, ids in sorted(values, key=lambda item: len(item[0]), reverse=True):
        pattern = r"(?<!\w)" + re.escape(value) + r"(?!\w)"
        if re.search(pattern, remaining):
            criteria[key].extend(sorted(ids) if ids else [value])
            remaining = re.sub(pattern, " ", remaining)
    # Reject unsupported predicates instead of silently broadening the audience.
    fillers = set(
        "send prepare start initiate launch request requests questionnaire questionnaires "
        "supplier suppliers to for the a an in region regions industry industries sector "
        "who that are is and please located based operating from with of all".split()
    )
    tokens = re.findall(r"[\w'-]+|[^\w\s,.;:!?\"()]", remaining)
    unknown = set(tokens) - fillers
    if unknown:
        fail(
            "Could not interpret: "
            + ", ".join(sorted(unknown))
            + ". Use supplier names or IDs, region and industry joined with 'and'. "
            "Other filters, exclusions and 'or' are not supported.",
            422,
        )
    if len(criteria["region"]) > 1 or len(criteria["industry"]) > 1:
        fail("Use one region and one industry per request; named suppliers can be combined with 'and'.", 422)
    if not any(criteria[key] for key in ("region", "industry", "supplier_ids")) and "all" not in tokens:
        fail("Name suppliers, specify a region or industry, or explicitly request all suppliers.", 422)
    criteria["supplier_ids"] = sorted(set(criteria["supplier_ids"]))
    return criteria


def candidate(db, case, fields, criteria, settings):
    attrs = profile(fields)
    for key in ("region", "industry"):
        if criteria[key] and attrs[key] not in criteria[key]:
            return None
    if criteria["supplier_ids"] and case.supplier_id not in criteria["supplier_ids"]:
        return None
    requested = [
        f
        for f in fields
        if normalized(f.data["Use case"]) == "mdf"
        and f.data["Status"] in OUTSTANDING
        and f.data["Editable by supplier"].lower() == "yes"
    ]
    reason = None
    if not requested:
        reason = "No outstanding MDF fields"
    elif not case.recipient:
        reason = "Approve a supplier email contact first"
    elif settings.mail_mode == "gmail" and case.recipient.casefold() != settings.gmail_supplier.casefold():
        reason = "Recipient is outside the configured Gmail test address"
    elif pending_review(db, case.id) or blocking_message(db, case.id):
        reason = "Review the supplier reply first"
    elif db.scalar(select(Draft.id).where(Draft.case_id == case.id, Draft.status.in_(ACTIVE_DRAFTS))):
        reason = "An email is already active; review the existing request"
    elif case.status == "awaiting_reply":
        reason = "Waiting for the supplier reply"
    elif case.status in {"paused", "escalated", "closed"}:
        reason = "Review this case individually before restarting"
    return {
        "id": case.id,
        "supplier_id": case.supplier_id,
        "supplier_name": case.supplier_name,
        "nart": case.nart,
        "recipient": case.recipient,
        **attrs,
        "revision": case.revision,
        "fields": [{"id": f.id, "revision": f.revision, "label": f.data["Field (label)"]} for f in requested],
        "eligible": reason is None,
        "reason": reason,
    }


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def install_initiation_routes(app, settings, DB, Reviewer):
    signer = URLSafeTimedSerializer(settings.nova_reviewer_token.get_secret_value(), salt="process-preview")

    @app.post("/processes/preview", tags=["Processes"])
    def preview(body: ProcessPreview, db: DB, actor: Reviewer):
        cases = db.scalars(select(Case).order_by(Case.id)).all()
        fields = db.scalars(select(SupplierField).order_by(SupplierField.id)).all()
        criteria = parse_command(body.command, cases, fields)
        by_case = {}
        for field in fields:
            by_case.setdefault(field.case_id, []).append(field)
        matches = []
        missing = 0
        for case in cases:
            rows = by_case.get(case.id, [])
            attrs = profile(rows)
            if any(criteria[key] and not attrs[key] for key in ("region", "industry")):
                missing += 1
            item = candidate(db, case, rows, criteria, settings)
            if item:
                matches.append(item)
                if len(matches) > 500:
                    fail("More than 500 article cases match. Narrow the audience before starting.", 422)
        token = signer.dumps(
            {
                "actor": actor,
                "command": body.command,
                "criteria": criteria,
                "snapshots": {item["id"]: fingerprint(item) for item in matches if item["eligible"]},
            }
        )
        return {
            "criteria": criteria,
            "matches": matches,
            "supplier_count": len({item["supplier_id"] for item in matches}),
            "missing_metadata_count": missing,
            "preview_token": token,
        }

    @app.post("/processes/start", tags=["Processes"])
    def start(body: ProcessStart, db: DB, actor: Reviewer):
        try:
            preview = signer.loads(body.preview_token, max_age=1800)
        except BadSignature:
            fail("Preview expired or invalid; preview the request again.")
        if preview["actor"] != actor:
            fail("Preview belongs to another reviewer", 403)
        ids = sorted(set(body.case_ids))
        if any(case_id not in preview["snapshots"] for case_id in ids):
            fail("Select only eligible cases from the preview", 422)
        # Consistent case lock order; validate the whole selection before drafting any emails.
        selected = [locked(db, Case, case_id) for case_id in ids]
        for case in selected:
            fields = db.scalars(
                select(SupplierField).where(SupplierField.case_id == case.id).order_by(SupplierField.id)
            ).all()
            item = candidate(db, case, fields, preview["criteria"], settings)
            if not item or fingerprint(item) != preview["snapshots"][case.id]:
                fail("A selected case changed; preview the request again before starting.")
        drafts = []
        for case in selected:
            draft = create_draft(db, case, "request" if not case.last_sent_at else "followup", use_case="MDF")
            audit(
                db,
                actor,
                "process.initiated",
                case.id,
                command=preview["command"],
                criteria=preview["criteria"],
                draft_id=draft.id,
            )
            drafts.append({"id": draft.id, "case_id": case.id, "status": draft.status})
        return {"drafts": drafts}
