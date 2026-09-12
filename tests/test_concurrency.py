from concurrent.futures import ThreadPoolExecutor

import pytest

from nova.worker import run_once
from tests.conftest import AUTOMATION, REVIEW, approve_email, seed


def test_concurrent_triggers_approvals_and_workers_do_not_duplicate_send(env):
    client, factory, settings = env
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("Row-lock concurrency is verified against PostgreSQL")
    seed(client)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post("/automation/tick", headers=AUTOMATION), range(4)))
    assert all(r.status_code == 200 for r in responses)
    drafts = client.get("/drafts", headers=REVIEW).json()
    assert len(drafts) == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: approve_email(client, drafts[0]), range(4)))
    assert len(client.get("/jobs", headers=REVIEW).json()) == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: run_once(factory, settings), range(4)))
    assert sum(results) == 1
    assert client.get("/drafts", headers=REVIEW).json()[0]["status"] == "simulated"
    sends = [a for a in client.get("/audit", headers=REVIEW).json() if a["action"] == "email.simulated"]
    assert len(sends) == 1
