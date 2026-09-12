from nova.models import Draft, SupplierField
from nova.worker import run_once
from tests.conftest import AUTOMATION, REVIEW, approve_email, reply, request_draft, seed


def login(client):
    response = client.post(
        "/api/session", json={"token": "review-secret"}, headers={"Origin": "http://testserver"}
    )
    assert response.status_code == 200, response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    assert "review-secret" not in response.headers["set-cookie"]
    return {"X-NOVA-CSRF": response.json()["csrf"]}


def test_browser_session_requires_reviewer_and_csrf(env):
    client, factory, settings = env
    case_id = seed(client)
    draft = request_draft(client, case_id)
    assert client.get("/api/cases").status_code == 401
    assert (
        client.post(
            "/api/session", json={"token": "automation-secret"}, headers={"Origin": "http://testserver"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/session",
            json={"token": "review-secret"},
            headers={"Origin": "https://another-site.example"},
        ).status_code
        == 403
    )
    csrf = login(client)
    assert client.get("/api/cases").json()[0]["id"] == case_id
    path = f"/api/drafts/{draft['id']}/approve"
    assert client.post(path, json={"version": 1}).status_code == 403
    assert client.post(path, json={"version": 1}, headers=csrf).status_code == 200
    run_once(factory, settings)
    with factory() as db:
        assert db.get(Draft, draft["id"]).status == "simulated"
    assert client.delete("/api/session", headers=csrf).status_code == 204
    assert client.get("/api/cases").status_code == 401
    assert client.get("/api/session").json() == {"authenticated": False}
    assert client.get("/cases", headers=REVIEW).status_code == 200
    assert client.post("/api/automation/tick", headers=AUTOMATION).status_code == 200


def test_browser_data_approval_and_case_evidence(env):
    client, factory, settings = env
    case_id = seed(client)
    draft = request_draft(client, case_id)
    approve_email(client, draft)
    run_once(factory, settings)
    message = reply(client, case_id)
    run_once(factory, settings)
    csrf = login(client)
    messages = client.get(f"/api/cases/{case_id}/messages").json()
    assert messages[0]["id"] == message["id"]
    assert messages[0]["body"] == "F1=Confirmed composition"
    assert client.get(f"/api/cases/{case_id}/activity").json()
    assert len(client.get(f"/api/jobs?case_id={case_id}").json()) == 2
    proposal = client.get(f"/api/proposals?case_id={case_id}").json()[0]
    with factory() as db:
        assert db.get(SupplierField, "F1").data["Value submitted"] == ""
    result = client.post(
        f"/api/proposals/{proposal['id']}/approve", json={"version": proposal["version"]}, headers=csrf
    )
    assert result.status_code == 200
    with factory() as db:
        assert db.get(SupplierField, "F1").data["Value submitted"] == "Confirmed composition"
