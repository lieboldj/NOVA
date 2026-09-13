"""Deploy the approved NOVA demo project; secrets stay in ignored local files and Secret Manager.

Run phases separately for resumable provisioning: identities, database, build, deploy.
Initial API enablement, SQL instance, artifact repository and bucket are documented in cloud-deployment.md.
"""

import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path

from nova.config import get_settings

PROJECT = "aiwomen26ham-4415"
REGION = "europe-west3"
SQL = f"{PROJECT}:{REGION}:nova-db"
BUCKET = f"{PROJECT}-nova-evidence"
REGISTRY = f"{REGION}-docker.pkg.dev"
N8N_VERSION = "2.38.7"
# The lab grants Editor to this runtime identity and does not allow the deployment
# user to change project IAM. Use its existing authorized SQL access; bind secrets
# at resource scope. Dedicated least-privilege accounts need the project IAM admin.
RUNTIME_ACCOUNT = "1048492379133-compute@developer.gserviceaccount.com"
ROOT = Path(".data/cloud")
GCLOUD = str(Path.home() / "google-cloud-sdk/bin/gcloud")


def command(args, *, data=None, required=True):
    result = subprocess.run(args, input=data, capture_output=True, text=True)
    if required and result.returncode:
        # Never echo command arguments: some provisioning commands accept secret parameters.
        error = result.stderr
        if (ROOT / "secrets.json").exists():
            for value in json.loads((ROOT / "secrets.json").read_text()).values():
                if isinstance(value, str) and len(value) > 6:
                    error = error.replace(value, "[REDACTED]")
        raise RuntimeError(error)
    return result


def gc(*args, required=True, data=None):
    return command([GCLOUD, *args, f"--project={PROJECT}", "--quiet"], required=required, data=data)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def values():
    path = ROOT / "secrets.json"
    if path.exists():
        return json.loads(path.read_text())
    settings = get_settings()
    result = {
        "NOVA_REVIEWER_TOKEN": secrets.token_urlsafe(36),
        "NOVA_AUTOMATION_TOKEN": secrets.token_urlsafe(36),
        "NOVA_DB_PASSWORD": secrets.token_urlsafe(32),
        "N8N_DB_PASSWORD": secrets.token_urlsafe(32),
        "N8N_ENCRYPTION_KEY": secrets.token_hex(32),
        "N8N_OWNER_PASSWORD": secrets.token_urlsafe(24) + "Aa1!",
    }
    for key in (
        "GEMINI_API_KEY",
        "ANYMIZE_API_KEY",
        "GMAIL_CLIENT_ID",
        "GMAIL_CLIENT_SECRET",
        "GMAIL_REFRESH_TOKEN",
    ):
        result[key] = getattr(settings, key.lower()).get_secret_value()
        if not result[key]:
            raise RuntimeError(f"Missing local {key}; provision credentials first.")
    result["DATABASE_URL"] = (
        f"postgresql+psycopg://nova:{result['NOVA_DB_PASSWORD']}@/nova?host=/cloudsql/{SQL}"
    )
    save(path, result)
    return result


def service_account(name):
    return RUNTIME_ACCOUNT


def secret_name(key):
    return "nova-" + key.lower().replace("_", "-")


def identities():
    vals = values()
    for name in ("nova-api", "nova-worker", "nova-n8n"):
        if gc("iam", "service-accounts", "describe", service_account(name), required=False).returncode:
            gc("iam", "service-accounts", "create", name, f"--display-name={name}")
        print("Runtime identity ready:", name, flush=True)
    for name in ("nova-api", "nova-worker"):
        gc(
            "storage",
            "buckets",
            "add-iam-policy-binding",
            f"gs://{BUCKET}",
            f"--member=serviceAccount:{service_account(name)}",
            "--role=" + ("roles/storage.objectUser" if name == "nova-api" else "roles/storage.objectViewer"),
        )
    for key, value in vals.items():
        name = secret_name(key)
        if gc("secrets", "describe", name, required=False).returncode:
            gc("secrets", "create", name, "--replication-policy=user-managed", f"--locations={REGION}")
            gc("secrets", "versions", "add", name, "--data-file=-", data=value)
        principals = []
        if key in ("N8N_DB_PASSWORD", "N8N_ENCRYPTION_KEY"):
            principals = ["nova-n8n"]
        elif key not in ("N8N_OWNER_PASSWORD", "NOVA_DB_PASSWORD"):
            principals = ["nova-api", "nova-worker"]
            if key in ("NOVA_REVIEWER_TOKEN", "NOVA_AUTOMATION_TOKEN"):
                principals = ["nova-api"]
        for principal in principals:
            gc(
                "secrets",
                "add-iam-policy-binding",
                name,
                f"--member=serviceAccount:{service_account(principal)}",
                "--role=roles/secretmanager.secretAccessor",
            )
        print("Secret ready:", key, flush=True)


def database():
    vals = values()
    status = json.loads(gc("sql", "instances", "describe", "nova-db", "--format=json").stdout)
    if status["state"] != "RUNNABLE":
        raise RuntimeError("Cloud SQL provisioning is still running; resume the database phase when ready.")
    dbs = json.loads(gc("sql", "databases", "list", "--instance=nova-db", "--format=json").stdout)
    users = json.loads(gc("sql", "users", "list", "--instance=nova-db", "--format=json").stdout)
    for name, password in (("nova", vals["NOVA_DB_PASSWORD"]), ("n8n", vals["N8N_DB_PASSWORD"])):
        if name not in [d["name"] for d in dbs]:
            gc("sql", "databases", "create", name, "--instance=nova-db")
        if name not in [u["name"] for u in users]:
            gc("sql", "users", "create", name, "--instance=nova-db", f"--password={password}")
        print("Database and user ready:", name, flush=True)


def build():
    revision = command(["git", "rev-parse", "--short=12", "HEAD"]).stdout.strip()
    image = f"{REGISTRY}/{PROJECT}/nova/app:{revision}"
    n8n = f"{REGISTRY}/{PROJECT}/nova/n8n:{N8N_VERSION}"
    config = {
        "steps": [
            {"name": "gcr.io/cloud-builders/docker", "args": ["build", "-t", image, "."]},
            {"name": "gcr.io/cloud-builders/docker", "args": ["push", image]},
            {
                "name": "gcr.io/go-containerregistry/crane:debug",
                "args": ["copy", "--platform=linux/amd64", f"ghcr.io/n8n-io/n8n:{N8N_VERSION}", n8n],
            },
        ],
        "images": [image],
        "options": {"logging": "CLOUD_LOGGING_ONLY"},
        "timeout": "1200s",
    }
    save(ROOT / "build.json", config)
    print("Building and uploading images inside Google Cloud.", flush=True)
    gc(
        "builds",
        "submit",
        ".",
        f"--region={REGION}",
        f"--config={ROOT / 'build.json'}",
        "--ignore-file=.dockerignore",
        f"--service-account=projects/{PROJECT}/serviceAccounts/{RUNTIME_ACCOUNT}",
        "--default-buckets-behavior=regional-user-owned-bucket",
    )
    save(ROOT / "images.json", {"nova": image, "n8n": n8n})
    print("NOVA and pinned n8n images pushed.", flush=True)


def deploy():
    images = json.loads((ROOT / "images.json").read_text())
    settings = get_settings()
    common = {
        "AI_MODE": "gemini",
        "ANONYMIZER_MODE": "anymize",
        "MAIL_MODE": "gmail",
        "GEMINI_MODEL": settings.gemini_model,
        "ANYMIZE_BASE_URL": settings.anymize_base_url,
        "GMAIL_MAILBOX": settings.gmail_mailbox,
        "GMAIL_SUPPLIER": settings.gmail_mailbox,
        "STORAGE_BUCKET": BUCKET,
        "NOVA_COOKIE_SECURE": "true",
        "NOVA_REVIEWER_NAME": "demo-reviewer",
        "FORWARDED_ALLOW_IPS": "*",
    }
    if (ROOT / "gmail-push.json").exists():
        common.update(json.loads((ROOT / "gmail-push.json").read_text()))
    save(ROOT / "nova-env.json", common)
    keys = [
        "DATABASE_URL",
        "GEMINI_API_KEY",
        "ANYMIZE_API_KEY",
        "GMAIL_CLIENT_ID",
        "GMAIL_CLIENT_SECRET",
        "GMAIL_REFRESH_TOKEN",
    ]

    def refs(items):
        return ",".join(f"{k}={secret_name(k)}:1" for k in items)

    gc(
        "run",
        "jobs",
        "deploy",
        "nova-migrate",
        f"--region={REGION}",
        f"--image={images['nova']}",
        f"--service-account={service_account('nova-api')}",
        f"--set-cloudsql-instances={SQL}",
        f"--set-secrets={refs(['DATABASE_URL'])}",
        "--command=alembic",
        "--args=upgrade,head",
        "--tasks=1",
        "--max-retries=0",
        "--task-timeout=300s",
        "--memory=512Mi",
    )
    gc("run", "jobs", "execute", "nova-migrate", f"--region={REGION}", "--wait")
    print("Database migrations completed.", flush=True)
    for name, is_worker in (("nova", False), ("nova-worker", True)):
        args = [
            "run",
            "deploy",
            name,
            f"--region={REGION}",
            f"--image={images['nova']}",
            f"--service-account={service_account('nova-worker' if is_worker else 'nova-api')}",
            f"--add-cloudsql-instances={SQL}",
            f"--env-vars-file={ROOT / 'nova-env.json'}",
            f"--set-secrets={refs(keys if is_worker else keys + ['NOVA_REVIEWER_TOKEN', 'NOVA_AUTOMATION_TOKEN'])}",
            "--port=8000",
            "--cpu=1",
            "--memory=512Mi",
            "--timeout=300s",
            "--max-instances=1" if is_worker else "--max-instances=2",
            "--min-instances=1" if is_worker else "--min-instances=0",
            "--concurrency=1" if is_worker else "--concurrency=20",
            "--no-allow-unauthenticated" if is_worker else "--allow-unauthenticated",
        ]
        if is_worker:
            args += [
                "--no-cpu-throttling",
                "--command=uvicorn",
                "--args=nova.cloud_worker:app,--host,0.0.0.0,--port,8000",
            ]
        gc(*args)
        print("Service deployed:", name, flush=True)
    deploy_n8n()


def deploy_n8n():
    images = json.loads((ROOT / "images.json").read_text())
    api_url = gc(
        "run", "services", "describe", "nova", f"--region={REGION}", "--format=value(status.url)"
    ).stdout.strip()
    n8n_env = {
        "DB_TYPE": "postgresdb",
        "DB_POSTGRESDB_HOST": f"/cloudsql/{SQL}",
        "DB_POSTGRESDB_DATABASE": "n8n",
        "DB_POSTGRESDB_USER": "n8n",
        "DB_POSTGRESDB_POOL_SIZE": "3",
        "N8N_PORT": "5678",
        "N8N_PROTOCOL": "https",
        "N8N_PROXY_HOPS": "1",
        "GENERIC_TIMEZONE": "Europe/Berlin",
        "TZ": "Europe/Berlin",
        "N8N_DIAGNOSTICS_ENABLED": "false",
        "N8N_PERSONALIZATION_ENABLED": "false",
        "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
        "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS": "true",
        "N8N_DEFAULT_BINARY_DATA_MODE": "database",
        "EXECUTIONS_DATA_MAX_AGE": "168",
        "EXECUTIONS_DATA_SAVE_ON_SUCCESS": "all",
        "EXECUTIONS_DATA_SAVE_ON_ERROR": "all",
    }
    save(ROOT / "n8n-env.json", n8n_env)
    gc(
        "run",
        "deploy",
        "nova-n8n",
        f"--region={REGION}",
        f"--image={images['n8n']}",
        f"--service-account={service_account('nova-n8n')}",
        f"--add-cloudsql-instances={SQL}",
        f"--env-vars-file={ROOT / 'n8n-env.json'}",
        f"--set-secrets=DB_POSTGRESDB_PASSWORD={secret_name('N8N_DB_PASSWORD')}:1,N8N_ENCRYPTION_KEY={secret_name('N8N_ENCRYPTION_KEY')}:1",
        "--port=5678",
        "--cpu=1",
        "--memory=1Gi",
        "--min-instances=1",
        "--max-instances=1",
        "--no-cpu-throttling",
        "--concurrency=20",
        "--no-allow-unauthenticated",
        "--timeout=300s",
    )
    n8n_url = gc(
        "run", "services", "describe", "nova-n8n", f"--region={REGION}", "--format=value(status.url)"
    ).stdout.strip()
    gc(
        "run",
        "services",
        "update",
        "nova-n8n",
        f"--region={REGION}",
        f"--update-env-vars=N8N_HOST={n8n_url.removeprefix('https://')},N8N_EDITOR_BASE_URL={n8n_url},WEBHOOK_URL={n8n_url}/",
    )
    save(ROOT / "urls.json", {"nova": api_url, "n8n": n8n_url})
    print("NOVA URL:", api_url, flush=True)
    print("n8n deployed privately for owner setup:", n8n_url, flush=True)


if __name__ == "__main__":
    os.umask(0o077)
    ROOT.mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["identities", "database", "build", "deploy", "deploy_n8n"])
    args = parser.parse_args()
    globals()[args.phase]()
