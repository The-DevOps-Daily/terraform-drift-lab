#!/usr/bin/env python3
"""Delete the resources the scenarios created outside Terraform.

Reads .lab/outside.json, then sweeps by name in case a run died before writing it.
"""
import json
import subprocess

from common import ZONE, doctl
from scenarios import OUTSIDE

NAMES = {"droplet": {"dl-web-debug", "dl-scratch-1"}, "firewall": {"dl-hotfix-8080"}}


def run(*args):
    p = subprocess.run(["doctl", *args], capture_output=True, text=True)
    return p.returncode == 0 or "404" in p.stderr or "not found" in p.stderr.lower()


def main():
    items = json.loads(OUTSIDE.read_text()) if OUTSIDE.exists() else []
    for d in doctl("compute", "droplet", "list") or []:
        if d["name"] in NAMES["droplet"]:
            items.append({"type": "droplet", "id": str(d["id"]), "name": d["name"]})
    for f in doctl("compute", "firewall", "list") or []:
        if f["name"] in NAMES["firewall"]:
            items.append({"type": "firewall", "id": f["id"], "name": f["name"]})
    done = set()
    for it in items:
        key = (it["type"], it["id"])
        if key in done:
            continue
        done.add(key)
        if it["type"] == "droplet":
            ok = run("compute", "droplet", "delete", it["id"], "--force")
        elif it["type"] == "firewall":
            ok = run("compute", "firewall", "delete", it["id"], "--force")
        elif it["type"] == "record":
            ok = run("compute", "domain", "records", "delete", ZONE, it["id"], "--force")
        elif it["type"] == "tag":
            ok = run("compute", "tag", "delete", it["id"], "--force")
        else:
            ok = False
        print(f"deleted {it['type']} {it['name']}" if ok else f"FAILED to delete {it}")
    OUTSIDE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
