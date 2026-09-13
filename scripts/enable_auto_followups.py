"""Deploy the explicitly authorized automatic-follow-up policy to the existing cloud services."""

import json
import re
from pathlib import Path

from scripts.deploy_cloud import REGION, ROOT, gc, save


def main():
    image = json.loads((ROOT / "images.json").read_text())["nova"]
    for name in ("nova", "nova-worker"):
        gc(
            "run",
            "services",
            "update",
            name,
            f"--region={REGION}",
            f"--image={image}",
            "--update-env-vars=AUTO_FOLLOWUP_ENABLED=true,AUTO_FOLLOWUP_MAX_ROUNDS=3",
        )
        print(name + ": automatic follow-ups enabled (maximum three rounds)", flush=True)
    path = Path(".env")
    content = path.read_text()
    for key, value in {"AUTO_FOLLOWUP_ENABLED": "true", "AUTO_FOLLOWUP_MAX_ROUNDS": "3"}.items():
        if re.search(r"^" + key + "=", content, re.M):
            content = re.sub(r"^" + key + "=.*$", key + "=" + value, content, flags=re.M)
        else:
            content += "\n" + key + "=" + value + "\n"
    path.write_text(content)
    env = json.loads((ROOT / "nova-env.json").read_text())
    env.update(AUTO_FOLLOWUP_ENABLED="true", AUTO_FOLLOWUP_MAX_ROUNDS="3")
    save(ROOT / "nova-env.json", env)


if __name__ == "__main__":
    main()
