"""Continuous worker for an instance-billed Cloud Run service with minimum instances=1.

Only a health endpoint is exposed, behind Cloud Run IAM. Work still comes exclusively
from durable, approval-gated database jobs. Interrupted sends are never blindly retried.
"""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from nova.config import get_settings
from nova.db import make_engine, sessions
from nova.worker import run_once


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    engine = make_engine(settings.database_url)
    factory = sessions(engine)
    stopped = threading.Event()

    def work():
        while not stopped.is_set():
            try:
                worked = run_once(factory, settings)
            except Exception:
                # Keep polling after transient DB failures. Never log provider content or secrets.
                print("Worker database unavailable; retrying.", flush=True)
                worked = False
            if not worked:
                stopped.wait(settings.worker_poll_seconds)

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    app.state.worker_thread = thread
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=5)
        engine.dispose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health():
    return Response(status_code=200 if app.state.worker_thread.is_alive() else 503)
