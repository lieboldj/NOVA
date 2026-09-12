"""Local developer client: credentials are read from .env and never printed."""

import argparse
import json
from pathlib import Path

import httpx

from nova.config import get_settings

parser = argparse.ArgumentParser()
parser.add_argument("method", choices=["GET", "POST", "PATCH"])
parser.add_argument("path")
parser.add_argument("--json", default=None)
parser.add_argument("--file", type=Path, help="CSV file for POST /imports")
parser.add_argument("--url", default="http://127.0.0.1:8000")
parser.add_argument("--role", choices=["reviewer", "automation"], default="reviewer")
args = parser.parse_args()
settings = get_settings()
token = settings.nova_reviewer_token if args.role == "reviewer" else settings.nova_automation_token
kwargs = {"headers": {"Authorization": "Bearer " + token.get_secret_value()}, "timeout": 120}
if args.json:
    kwargs["json"] = json.loads(args.json)
if args.file:
    kwargs["files"] = {"file": (args.file.name, args.file.read_bytes(), "text/csv")}
try:
    response = httpx.request(args.method, args.url.rstrip("/") + args.path, **kwargs)
    print("HTTP", response.status_code)
    if "application/json" in response.headers.get("content-type", ""):
        print(json.dumps(response.json(), indent=2))
    else:
        print(response.text)
    raise SystemExit(0 if response.is_success else 1)
except httpx.HTTPError:
    print("NOVA request failed. Check the backend address and server status.")
    raise SystemExit(1) from None
