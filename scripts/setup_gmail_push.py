"""Provision authenticated Gmail push; update only NOVA API, keeping worker/n8n running."""

import argparse
import json

import httpx

from scripts.deploy_cloud import PROJECT, REGION, ROOT, gc, save, values

TOPIC = "nova-gmail-inbox"
SUBSCRIPTION = "nova-gmail-to-nova"
ACCOUNT = f"nova-gmail-push@{PROJECT}.iam.gserviceaccount.com"


def prepare():
    vals = values()
    number = gc("projects", "describe", PROJECT, "--format=value(projectNumber)").stdout.strip()
    if vals["GMAIL_CLIENT_ID"].split("-")[0] != number:
        raise RuntimeError("Gmail OAuth client and Pub/Sub topic must use the same project")
    gc("services", "enable", "pubsub.googleapis.com")
    access = gc("auth", "print-access-token").stdout.strip()
    identity = httpx.post(
        f"https://serviceusage.googleapis.com/v1beta1/projects/{number}/services/pubsub.googleapis.com:generateServiceIdentity",
        headers={"Authorization": "Bearer " + access},
        json={},
        timeout=60,
    )
    if not identity.is_success:
        raise RuntimeError(f"Pub/Sub service identity failed: HTTP {identity.status_code}")
    if gc("pubsub", "topics", "describe", TOPIC, required=False).returncode:
        gc("pubsub", "topics", "create", TOPIC, f"--message-storage-policy-allowed-regions={REGION}")
    gc(
        "pubsub",
        "topics",
        "add-iam-policy-binding",
        TOPIC,
        "--member=serviceAccount:gmail-api-push@system.gserviceaccount.com",
        "--role=roles/pubsub.publisher",
    )
    if gc("iam", "service-accounts", "describe", ACCOUNT, required=False).returncode:
        gc("iam", "service-accounts", "create", "nova-gmail-push")
    gc(
        "iam",
        "service-accounts",
        "add-iam-policy-binding",
        ACCOUNT,
        f"--member=serviceAccount:service-{number}@gcp-sa-pubsub.iam.gserviceaccount.com",
        "--role=roles/iam.serviceAccountTokenCreator",
    )
    urls = json.loads((ROOT / "urls.json").read_text())
    save(
        ROOT / "gmail-push.json",
        {
            "GMAIL_PUSH_TOPIC": f"projects/{PROJECT}/topics/{TOPIC}",
            "GMAIL_PUSH_SUBSCRIPTION": f"projects/{PROJECT}/subscriptions/{SUBSCRIPTION}",
            "GMAIL_PUSH_SERVICE_ACCOUNT": ACCOUNT,
            "GMAIL_PUSH_AUDIENCE": urls["nova"] + "/mail/gmail/push",
            "GMAIL_PUSH_WEBHOOK": urls["n8n"] + "/webhook/nova-gmail-push",
        },
    )
    print("Gmail push topic and restricted signing identity ready", flush=True)


def deploy():
    config = json.loads((ROOT / "gmail-push.json").read_text())
    images = json.loads((ROOT / "images.json").read_text())
    gc(
        "run",
        "services",
        "update",
        "nova",
        f"--region={REGION}",
        f"--image={images['nova']}",
        "--update-env-vars=" + ",".join(f"{k}={v}" for k, v in config.items()),
    )
    print("NOVA authenticated push receiver deployed", flush=True)


def activate():
    config = json.loads((ROOT / "gmail-push.json").read_text())
    endpoint = config["GMAIL_PUSH_AUDIENCE"]
    if gc("pubsub", "subscriptions", "describe", SUBSCRIPTION, required=False).returncode:
        gc(
            "pubsub",
            "subscriptions",
            "create",
            SUBSCRIPTION,
            f"--topic={TOPIC}",
            f"--push-endpoint={endpoint}",
            f"--push-auth-service-account={ACCOUNT}",
            f"--push-auth-token-audience={endpoint}",
            "--ack-deadline=300",
            "--min-retry-delay=10s",
            "--max-retry-delay=600s",
            "--expiration-period=never",
        )
    urls = json.loads((ROOT / "urls.json").read_text())
    response = httpx.post(
        urls["nova"] + "/automation/gmail/watch",
        headers={"Authorization": "Bearer " + values()["NOVA_AUTOMATION_TOKEN"]},
        timeout=60,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Gmail watch registration failed: HTTP {response.status_code}")
    save(ROOT / "gmail-watch.json", response.json())
    print("Gmail push watch active; daily n8n workflow renews it", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "deploy", "activate"])
    globals()[parser.parse_args().phase]()
