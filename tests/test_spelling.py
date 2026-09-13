from types import SimpleNamespace

from nova.providers import FixtureEvaluator
from nova.schemas import Evaluation
from nova.spelling import eligible_correction
from nova.worker import run_once
from tests.conftest import REVIEW, approve_email, reply, request_draft, seed


def test_spelling_suggestions_preserve_quantities_and_identifiers():
    field = SimpleNamespace(data={"Field Type": "Freetext"}, rules={})
    original = "80% recylced aluminium"
    assert eligible_correction(field, original, "80% recycled aluminium", original)
    assert not eligible_correction(field, original, "90% recycled aluminium", original)
    assert not eligible_correction(field, original, "80% recycled aluminium", "unrelated evidence")
    assert not eligible_correction(
        field, "[[PERSON_1]] prodcut", "[[PERSON_2]] product", "[[PERSON_1]] prodcut"
    )
    assert not eligible_correction(field, "DEMO20-F1 prodcut", "DEMO20-F2 product", "DEMO20-F1 prodcut")
    assert not eligible_correction(field, "5 kg", "5 mg", "5 kg")
    field.data["Field Type"] = "Date"
    assert not eligible_correction(field, "2026-01-01", "2027-01-01", "2026-01-01")


def test_correction_is_separate_until_reviewer_edits_and_approves(env, monkeypatch):
    client, factory, settings = env
    case = seed(client)
    approve_email(client, request_draft(client, case))
    run_once(factory, settings)
    reply(client, case, "F1=80% recylced aluminium")

    def extract(self, fields, sources):
        return Evaluation(
            candidates=[
                {
                    "field_id": fields[0]["field_id"],
                    "value": "80% recylced aluminium",
                    "rationale": "Explicit supplier answer",
                    "evidence": {"source_id": "email", "quote": "80% recylced aluminium"},
                    "spelling_correction": {
                        "value": "80% recycled aluminium",
                        "reason": "Correct recylced to recycled",
                    },
                }
            ]
        )

    monkeypatch.setattr(FixtureEvaluator, "evaluate", extract)
    run_once(factory, settings)
    proposal = client.get("/proposals", headers=REVIEW).json()[0]
    assert proposal["value"] == "80% recylced aluminium"
    correction = proposal["evidence"]["spelling_correction"]
    assert correction["value"] == "80% recycled aluminium"
    assert client.get("/cases/" + case, headers=REVIEW).json()["fields"][0]["data"]["Value submitted"] == ""
    edited = client.patch(
        "/proposals/" + proposal["id"], headers=REVIEW, json={"version": 1, "value": correction["value"]}
    ).json()
    assert edited["version"] == 2
    assert (
        client.post(
            "/proposals/" + proposal["id"] + "/approve", headers=REVIEW, json={"version": 1}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/proposals/" + proposal["id"] + "/approve", headers=REVIEW, json={"version": 2}
        ).status_code
        == 200
    )
    current = client.get("/cases/" + case, headers=REVIEW).json()["fields"][0]
    assert current["data"]["Value submitted"] == "80% recycled aluminium"
    assert proposal["evidence"]["quote"] == "80% recylced aluminium"
