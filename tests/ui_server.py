"""Disposable UI test backend. Never uses .env, real Gmail, or the application database."""

import tempfile
import threading
import time
from pathlib import Path

import uvicorn

from nova.api import create_app
from nova.config import Settings
from nova.db import initialize
from nova.worker import run_once

with tempfile.TemporaryDirectory(prefix="nova-ui-test-") as directory:
    root = Path(directory)
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{root / 'nova_test.db'}",
        storage_path=root / "documents",
        nova_reviewer_token="ui-review-secret",
        nova_automation_token="ui-automation-secret",
        ai_mode="fixture",
        anonymizer_mode="fixture",
        mail_mode="simulation",
        gmail_client_id="",
        gmail_client_secret="",
        gmail_refresh_token="",
    )
    app = create_app(settings)
    initialize(app.state.engine)
    stopped = threading.Event()

    def worker():
        while not stopped.is_set():
            if not run_once(app.state.factory, settings):
                time.sleep(0.1)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=8011, log_level="warning")
    finally:
        stopped.set()
        thread.join(timeout=5)
