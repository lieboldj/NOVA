"""Authorize NOVA's internal Gmail account locally; never print or commit tokens."""

import argparse
import json
import os
from pathlib import Path

import httpx
from dotenv import set_key
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, default=Path(".data/gmail-client.json"))
    parser.add_argument("--mailbox", default="devstar4415@gcplab.me")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--output",
        type=Path,
        help="Save a separate authorized-user JSON instead of changing NOVA's .env sender credentials.",
    )
    args = parser.parse_args()
    if not args.client.is_file():
        parser.exit(1, "Save a Google Desktop OAuth client JSON in .data/gmail-client.json first.\n")
    os.chmod(args.client, 0o600)
    try:
        config = json.loads(args.client.read_text())
        if "installed" not in config:
            parser.exit(1, "Use a Desktop app OAuth client, not a web application client.\n")
        flow = InstalledAppFlow.from_client_config(config, SCOPES, autogenerate_code_verifier=True)
        credentials = flow.run_local_server(
            host="localhost",
            port=args.port,
            open_browser=True,
            login_hint=args.mailbox,
            prompt="consent",
            timeout_seconds=300,
            success_message="NOVA Gmail authorization received. You can close this window.",
        )
        response = httpx.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=30,
        )
        response.raise_for_status()
        if response.json()["emailAddress"].casefold() != args.mailbox.casefold():
            parser.exit(1, "Wrong Google account; no credentials saved. Retry with the internal mailbox.\n")
        if not credentials.refresh_token or not credentials.has_scopes(SCOPES):
            parser.exit(1, "Offline access and both Gmail permissions are required; no credentials saved.\n")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            # Create with restricted permissions before writing OAuth tokens.
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as output:
                output.write(credentials.to_json() + "\n")
            print("Gmail account verified; separate authorization saved privately. NOVA sender unchanged.")
            return
        env = Path(".env")
        env.touch(mode=0o600, exist_ok=True)
        os.chmod(env, 0o600)
        for key, value in {
            "MAIL_MODE": "gmail",
            "GMAIL_MAILBOX": args.mailbox,
            "GMAIL_SUPPLIER": "devstar4418@gcplab.me",
            "GMAIL_CLIENT_ID": credentials.client_id,
            "GMAIL_CLIENT_SECRET": credentials.client_secret,
            "GMAIL_REFRESH_TOKEN": credentials.refresh_token,
        }.items():
            set_key(str(env), key, value)
        print("Internal Gmail authorized. Credentials saved only to ignored .env. Restart API and worker.")
    except Exception:
        parser.exit(1, "Gmail authorization failed. Check OAuth client settings and account access; retry.\n")


if __name__ == "__main__":
    main()
