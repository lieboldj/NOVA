"""Configure the private n8n deployment, then expose its password-protected editor.

This only creates scheduler workflows and their NOVA automation credential. Neither
workflow can approve an email or supplier data. No original email content enters n8n.
"""

import json
import os

import httpx

from scripts.deploy_cloud import PROJECT, REGION, ROOT, gc, save, values


def main():
    os.umask(0o077)
    vals = values()
    urls = json.loads((ROOT / "urls.json").read_text())
    token = gc("auth", "print-identity-token").stdout.strip()
    state_path = ROOT / "n8n-setup.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    headers = {"X-Serverless-Authorization": "Bearer " + token, "Origin": urls["n8n"]}
    with httpx.Client(base_url=urls["n8n"], headers=headers, timeout=60) as client:

        def api(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if not response.is_success:
                # Response messages can contain credential data; do not print them.
                raise RuntimeError(f"n8n {method} {path} returned HTTP {response.status_code}")
            result = response.json()
            return result.get("data", result)

        if not state.get("owner"):
            api(
                "POST",
                "/rest/owner/setup",
                json={
                    "email": "devstar4415@gcplab.me",
                    "firstName": "NOVA",
                    "lastName": "Administrator",
                    "password": vals["N8N_OWNER_PASSWORD"],
                },
            )
            state["owner"] = True
            save(state_path, state)
        else:
            api(
                "POST",
                "/rest/login",
                json={
                    "emailOrLdapLoginId": "devstar4415@gcplab.me",
                    "password": vals["N8N_OWNER_PASSWORD"],
                },
            )
        if "credential_id" not in state:
            credential = api(
                "POST",
                "/rest/credentials",
                json={
                    "name": "NOVA automation only",
                    "type": "httpHeaderAuth",
                    "data": {"name": "Authorization", "value": "Bearer " + vals["NOVA_AUTOMATION_TOKEN"]},
                },
            )
            state["credential_id"] = credential["id"]
            save(state_path, state)
        from pathlib import Path

        filenames = ["check-pending-cases.json", "sync-gmail.json"]
        if (ROOT / "gmail-push.json").exists():
            filenames.append("renew-gmail-watch.json")
        for filename in filenames:
            template = json.loads((Path("integrations/n8n") / filename).read_text())
            for node in template["nodes"]:
                if node["type"] == "n8n-nodes-base.httpRequest":
                    node["parameters"]["url"] = node["parameters"]["url"].replace(
                        "http://api:8000", urls["nova"]
                    )
                    node["credentials"] = {
                        "httpHeaderAuth": {"id": state["credential_id"], "name": "NOVA automation only"}
                    }
                if node["type"] == "n8n-nodes-base.webhook":
                    node["credentials"] = {
                        "httpHeaderAuth": {"id": state["credential_id"], "name": "NOVA automation only"}
                    }
            if filename not in state:
                workflow = api(
                    "POST",
                    "/rest/workflows",
                    json={key: template[key] for key in ("name", "nodes", "connections", "settings")},
                )
                state[filename] = workflow["id"]
                save(state_path, state)
            workflow = api("GET", f"/rest/workflows/{state[filename]}")
            if any(workflow.get(key) != template[key] for key in ("nodes", "connections", "settings")):
                if workflow.get("active"):
                    api("POST", f"/rest/workflows/{workflow['id']}/deactivate")
                workflow = api(
                    "PATCH",
                    f"/rest/workflows/{workflow['id']}",
                    json={key: template[key] for key in ("name", "nodes", "connections", "settings")},
                )
            if not workflow.get("active"):
                api(
                    "POST",
                    f"/rest/workflows/{workflow['id']}/activate",
                    json={"versionId": workflow["versionId"]},
                )
            print("n8n workflow active:", template["name"], flush=True)
        gc(
            "run",
            "services",
            "add-iam-policy-binding",
            "nova-n8n",
            f"--region={REGION}",
            "--member=allUsers",
            "--role=roles/run.invoker",
        )
        print("n8n editor public; owner login required:", urls["n8n"], flush=True)
        access = (
            f"NOVA: {urls['nova']}\nReviewer access key: {vals['NOVA_REVIEWER_TOKEN']}\n\n"
            f"n8n: {urls['n8n']}\nEmail: devstar4415@gcplab.me\nPassword: {vals['N8N_OWNER_PASSWORD']}\n\n"
            f"Project: {PROJECT}\nRegion: {REGION}\n"
        )
        path = ROOT / "access.txt"
        path.write_text(access)
        path.chmod(0o600)
        print("Access details saved privately to", path, flush=True)


if __name__ == "__main__":
    main()
