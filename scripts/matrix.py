#!/usr/bin/env python3
"""Inject each drift scenario on its own, run every detector, then put the lab back.

For each scenario: confirm the lab is clean, inject, wait SETTLE seconds, run
  terraform plan -refresh-only -detailed-exitcode
  terraform plan -detailed-exitcode
  tofu plan -refresh-only -detailed-exitcode
  inventory.py
then delete what was created outside Terraform, apply, and confirm clean again.

A normal apply leaves computed counters stale (a tag's droplets_count changes
when a droplet is tagged or deleted after the tag was written to state), so the
next refresh-only plan exits 2 on a lab with no drift. After every revert we
record that plan, then run apply -refresh-only so the baseline starts settled.

Usage: matrix.py [rounds] [scenario ...]
Writes results/matrix-<time>.jsonl (first line is the stamp).
"""
import sys
import time

from common import RESULTS, TF, TOFU, append_jsonl, apply, now, plan, stamp, tag
import cleanup_outside
import inventory
from scenarios import SCENARIOS, ctx

SETTLE = 5


def clean():
    a = plan(TF, refresh_only=False)
    r = plan(TF, refresh_only=True)
    b = inventory.scan()
    ok = a["exit"] == 0 and r["exit"] == 0 and not b["unmanaged"] and not b["missing"]
    return ok, a, r, b


def ensure_clean(out, label):
    for attempt in range(3):
        ok, a, r, b = clean()
        append_jsonl(out, {"event": "baseline", "label": label, "attempt": attempt, "ok": ok,
                           "plan_exit": a["exit"], "plan_changes": a["changes"],
                           "refresh_only_exit": r["exit"], "refresh_only_drift": r["drift"],
                           "unmanaged": b["unmanaged"], "missing": b["missing"], "at": now()})
        if ok:
            return
        cleanup_outside.main()
        apply()
        apply(refresh_only=True)
        time.sleep(10)
    raise SystemExit(f"lab not clean before {label}, see {out}")


def main():
    args = sys.argv[1:]
    rounds = int(args.pop(0)) if args and args[0].isdigit() else 1
    names = args or list(SCENARIOS)
    out = RESULTS / f"matrix-{tag()}.jsonl"
    out.write_text(stamp("matrix.py") + f" rounds={rounds} settle={SETTLE}s\n")
    for rnd in range(1, rounds + 1):
        for name in names:
            ensure_clean(out, f"{rnd}:{name}")
            c = ctx()
            t0 = time.monotonic()
            facts = SCENARIOS[name](c)
            inject_s = round(time.monotonic() - t0, 1)
            time.sleep(SETTLE)
            row = {"event": "scenario", "round": rnd, "scenario": name, "injected_at": now(),
                   "inject_seconds": inject_s, **facts, "detectors": []}
            for det in (lambda: plan(TF, True), lambda: plan(TF, False), lambda: plan(TOFU, True), inventory.scan):
                row["detectors"].append(det())
            append_jsonl(out, row)
            summary = []
            for d in row["detectors"]:
                if d["tool"] == "inventory":
                    summary.append(f"inventory u={len(d['unmanaged'])} m={len(d['missing'])}")
                else:
                    summary.append(f"{d['tool']}/{d['mode']} exit={d['exit']} drift={len(d['drift'])} changes={len(d['changes'])}")
            print(f"[{rnd}] {name}: " + " | ".join(summary), flush=True)
            cleanup_outside.main()
            t1 = time.monotonic()
            apply()
            apply_s = round(time.monotonic() - t1, 1)
            after = plan(TF, True)
            apply(refresh_only=True)
            append_jsonl(out, {"event": "revert", "round": rnd, "scenario": name, "apply_seconds": apply_s,
                               "refresh_only_after_apply": {"exit": after["exit"], "drift": after["drift"]},
                               "at": now()})
    ensure_clean(out, "final")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
