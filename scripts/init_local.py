"""Add missing development API credentials without displaying or replacing secrets."""

import secrets
from pathlib import Path

from dotenv import dotenv_values

path = Path(".env")
existing = dotenv_values(path) if path.exists() else {}
additions = []
for key in ["NOVA_REVIEWER_TOKEN", "NOVA_AUTOMATION_TOKEN"]:
    if not existing.get(key):
        additions.append(f"{key}={secrets.token_urlsafe(32)}")
if additions:
    with path.open("a") as file:
        file.write("\n# NOVA local API credentials\n" + "\n".join(additions) + "\n")
    path.chmod(0o600)
print("Local API credentials configured in .env. No secret values displayed.")
