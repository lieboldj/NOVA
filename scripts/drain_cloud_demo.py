"""Bounded helper worker for an authorized demo burst; durable jobs keep approvals intact."""

import time

from nova.config import get_settings
from nova.db import make_engine, sessions
from nova.worker import run_once

settings = get_settings()
factory = sessions(make_engine(settings.database_url))
deadline = time.monotonic() + 600
idle_since = None
processed = 0
while time.monotonic() < deadline:
    if run_once(factory, settings):
        processed += 1
        idle_since = None
    else:
        idle_since = idle_since or time.monotonic()
        if time.monotonic() - idle_since > 15:
            break
        time.sleep(1)
print(f"Bounded helper completed {processed} durable jobs; no new approvals created.", flush=True)
