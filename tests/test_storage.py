from nova.worker import run_once
from tests.conftest import AUTOMATION, REVIEW, approve_email, reply, request_draft, seed


def test_cloud_evidence_is_shared_and_downloads_require_reviewer(env, monkeypatch):
    client, factory, settings = env
    settings.storage_bucket = "private-test-bucket"
    objects = {}

    class Blob:
        def __init__(self, key):
            self.key = key

        def upload_from_string(self, content, *, content_type, if_generation_match, timeout):
            assert if_generation_match == 0
            assert self.key not in objects
            objects[self.key] = content

        def download_as_bytes(self, *, timeout):
            return objects[self.key]

    class Client:
        def bucket(self, name):
            assert name == "private-test-bucket"
            return self

        def blob(self, key):
            assert key.startswith("documents/")
            return Blob(key)

    monkeypatch.setattr("nova.storage.cloud_client", lambda: Client())
    case = seed(client)
    approve_email(client, request_draft(client, case))
    run_once(factory, settings)
    message = reply(
        client,
        case,
        "See attached.",
        attachments=[
            ("attachments", ("supplier-évidence.txt", b"F1=Cloud evidence", "text/plain")),
        ],
    )
    assert not list(settings.storage_path.iterdir())
    run_once(factory, settings)
    proposal = client.get("/proposals", headers=REVIEW).json()[0]
    assert proposal["value"] == "Cloud evidence"
    doc = client.get(f"/messages/{message['id']}", headers=REVIEW).json()["documents"][0]
    url = f"/documents/{doc['id']}"
    assert client.get(url, headers=AUTOMATION).status_code == 403
    response = client.get(url, headers=REVIEW)
    assert response.content == b"F1=Cloud evidence"
    assert "supplier-%C3%A9vidence.txt" in response.headers["content-disposition"]
