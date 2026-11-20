#!/usr/bin/env python3
"""Cloud inventory diff: list what exists around the lab and compare it with the state.

Reports two things, like driftctl's default scan:
  unmanaged  exists in DigitalOcean, inside the lab's scope, but no state entry has its ID
  missing    the state has it, DigitalOcean does not

It compares IDs only. It does not compare attributes, so an edited firewall rule
or DNS value is invisible to it by design: that is the plan's job.

Scope (how the inventory decides what belongs to this stack), starting from the state:
  - every record in the lab zone, except the SOA and NS records DigitalOcean creates
  - every droplet in the lab project, or carrying a tag the state manages
  - every firewall that targets a lab droplet or a lab tag
  - every tag attached to a lab droplet
Anything outside that scope (a droplet with no lab tag in another project) is not seen.
"""
import json
import sys
import time

from common import Api, ZONE, state

AUTO_RECORDS = {"SOA", "NS"}


def managed():
    ids = {"droplet": set(), "firewall": set(), "tag": set(), "record": set(), "domain": set(), "project": set()}
    for r in state():
        v = r["values"]
        t = r["type"].removeprefix("digitalocean_")
        if t == "droplet":
            ids["droplet"].add(str(v["id"]))
        elif t == "firewall":
            ids["firewall"].add(v["id"])
        elif t == "tag":
            ids["tag"].add(v["name"])
        elif t == "record":
            ids["record"].add(str(v["id"]))
        elif t == "domain":
            ids["domain"].add(v["name"])
        elif t == "project":
            ids["project"].add(v["id"])
    return ids


def scan():
    api = Api()
    t0 = time.monotonic()
    want = managed()
    seen = {k: {} for k in want}

    for pid in want["project"]:
        status, body = api.get(f"/projects/{pid}/resources?per_page=200")
        if status == 200:
            seen["project"][pid] = "project"
            for res in body.get("resources", []):
                kind, _, rid = res["urn"].removeprefix("do:").partition(":")
                if kind == "droplet":
                    seen["droplet"][rid] = "in lab project"
                elif kind == "domain":
                    seen["domain"][rid] = "in lab project"

    status, _ = api.get(f"/domains/{ZONE}")
    if status == 200:
        seen["domain"][ZONE] = "zone"
        for rec in api.list(f"/domains/{ZONE}/records", "domain_records"):
            if rec["type"] not in AUTO_RECORDS:
                seen["record"][str(rec["id"])] = f"{rec['type']} {rec['name']} in zone"

    for t in sorted(want["tag"]):
        status, _ = api.get(f"/tags/{t}")
        if status == 200:
            seen["tag"][t] = "managed tag"
        for d in api.list(f"/droplets?tag_name={t}", "droplets"):
            seen["droplet"][str(d["id"])] = f"tagged {t}"

    lab_droplets = set(seen["droplet"]) | want["droplet"]
    for did in sorted(lab_droplets):
        status, body = api.get(f"/droplets/{did}")
        if status == 200:
            seen["droplet"].setdefault(did, "by id")
            for t in body["droplet"].get("tags", []):
                seen["tag"].setdefault(t, f"on droplet {did}")
        elif did in seen["droplet"]:
            del seen["droplet"][did]

    lab_tags = set(seen["tag"]) | want["tag"]
    live_droplets = set(seen["droplet"])
    for fw in api.list("/firewalls", "firewalls"):
        hits = {str(i) for i in fw.get("droplet_ids", [])} & live_droplets
        tags = set(fw.get("tags", [])) & lab_tags
        if hits or tags or fw["id"] in want["firewall"]:
            seen["firewall"][fw["id"]] = f"{fw['name']} targets " + ",".join(sorted(hits | tags) or ["nothing"])

    unmanaged, missing = [], []
    for kind in want:
        for rid, why in sorted(seen[kind].items()):
            if rid not in want[kind]:
                unmanaged.append({"type": kind, "id": rid, "why": why})
        for rid in sorted(want[kind]):
            if rid not in seen[kind]:
                missing.append({"type": kind, "id": rid})
    return {"tool": "inventory", "unmanaged": unmanaged, "missing": missing,
            "api_requests": api.requests, "seconds": round(time.monotonic() - t0, 2)}


if __name__ == "__main__":
    out = scan()
    print(json.dumps(out, indent=None if "--line" in sys.argv else 2))
    sys.exit(2 if out["unmanaged"] or out["missing"] else 0)
