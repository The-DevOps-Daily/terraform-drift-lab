#!/usr/bin/env python3
"""What the tag-removed drift does to the droplet: try port 22 before and after.

The managed firewall allows port 22 only from 203.0.113.0/24, a documentation
range, so from anywhere else a connection should time out. Removing the dl-web
tag takes the droplet out of the firewall. We record whether a TCP connect from
this machine succeeds and whether the SSH banner comes back, and what the plan
says about the firewall resource.

Writes results/exposure-<time>.json. Restores the lab at the end.
"""
import json
import socket
import time

from common import RESULTS, TF, apply, doctl, now, plan, stamp, tag
from scenarios import SCENARIOS, ctx


def probe(ip, port=22, timeout=5):
    t0 = time.monotonic()
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.settimeout(timeout)
            banner = s.recv(64).decode(errors="replace").strip()
            return {"connected": True, "banner": banner[:40], "seconds": round(time.monotonic() - t0, 2)}
    except OSError as e:
        return {"connected": False, "error": type(e).__name__, "seconds": round(time.monotonic() - t0, 2)}


def main():
    c = ctx()
    ip = doctl("compute", "droplet", "get", c["droplet"])[0]["networks"]["v4"]
    ip = next(n["ip_address"] for n in ip if n["type"] == "public")
    out = {"stamp": stamp("exposure.py"), "before": [], "after": []}
    for _ in range(3):
        out["before"].append(probe(ip))
    SCENARIOS["tag-removed"](c)
    out["tag_removed_at"] = now()
    # Firewall changes take a moment to reach the hypervisor; probe for up to two minutes.
    for _ in range(12):
        r = probe(ip)
        r["at"] = now()
        out["after"].append(r)
        if r["connected"]:
            break
        time.sleep(10)
    p = plan(TF, refresh_only=False)
    out["plan"] = {"exit": p["exit"], "changes": p["changes"],
                   "drift": [{"address": d["address"], "attrs": d["attrs"]} for d in p["drift"]]}
    apply()
    apply(refresh_only=True)
    time.sleep(20)
    out["restored"] = [probe(ip) for _ in range(3)]
    path = RESULTS / f"exposure-{tag()}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
