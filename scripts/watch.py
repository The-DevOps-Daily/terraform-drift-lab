#!/usr/bin/env python3
"""Time to detect: run the detectors on a schedule while drift lands at random times.

A scheduled refresh-only plan runs every PLAN_EVERY minutes and inventory.py every
INV_EVERY minutes, starting at t=0, for MINUTES minutes. Six scenarios are injected
at seeded random times. For each one we record the first detector run that started
after the injection and reported the scenario's signal, and the time from the
injection to the end of that run.

Usage: watch.py [seed]   Writes results/watch-<time>.jsonl. Restores the lab at the end.
"""
import os
import random
import sys
import time

from common import RESULTS, TF, append_jsonl, apply, now, plan, stamp, tag
import cleanup_outside
import inventory
from scenarios import SCENARIOS, ctx

MINUTES = int(os.environ.get("MINUTES", 60))
PLAN_EVERY = int(os.environ.get("PLAN_EVERY", 10))
INV_EVERY = int(os.environ.get("INV_EVERY", 2))
EVENTS = ["firewall-rule-added", "dns-hotfix", "tag-removed", "record-created",
          "firewall-created", "droplet-created-untagged"]


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 23
    rng = random.Random(seed)
    order = EVENTS[:]
    rng.shuffle(order)
    times = sorted(round(rng.uniform(1, MINUTES - 10), 2) for _ in order)
    timeline = [(m * 60.0, "plan", None) for m in range(0, MINUTES + 1, PLAN_EVERY)]
    timeline += [(m * 60.0, "inventory", None) for m in range(0, MINUTES + 1, INV_EVERY)]
    timeline += [(t * 60.0, "inject", name) for t, name in zip(times, order)]
    timeline.sort(key=lambda x: (x[0], x[1] != "inject"))
    out = RESULTS / f"watch-{tag()}.jsonl"
    out.write_text(stamp("watch.py") + f" seed={seed} minutes={MINUTES} plan_every={PLAN_EVERY}m "
                   f"inventory_every={INV_EVERY}m\n")
    start = time.monotonic()
    for at, kind, name in timeline:
        delay = at - (time.monotonic() - start)
        if delay > 0:
            time.sleep(delay)
        t_start = round(time.monotonic() - start, 1)
        if kind == "inject":
            facts = SCENARIOS[name](ctx())
            row = {"kind": "inject", "scenario": name, "planned_s": at, **facts}
        elif kind == "plan":
            r = plan(TF, True)
            row = {"kind": "plan", "exit": r["exit"], "drift": [d["address"] for d in r["drift"]],
                   "seconds": r["seconds"], "error": r.get("error")}
        else:
            r = inventory.scan()
            row = {"kind": "inventory", "unmanaged": r["unmanaged"], "missing": r["missing"],
                   "seconds": r["seconds"], "api_requests": r["api_requests"]}
        row.update({"t_start": t_start, "t_end": round(time.monotonic() - start, 1), "at": now()})
        append_jsonl(out, row)
        print(f"{row['t_start']:7.1f}s {kind} {name or ''} {row.get('drift', '')}"
              f"{[u['why'] for u in row.get('unmanaged', [])]}", flush=True)
    cleanup_outside.main()
    apply()
    apply(refresh_only=True)
    append_jsonl(out, {"kind": "restored", "at": now()})
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
