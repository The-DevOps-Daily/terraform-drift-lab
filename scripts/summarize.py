#!/usr/bin/env python3
"""Turn the raw result files into the tables in the README.

Usage: summarize.py matrix-<t>.jsonl [watch-<t>.jsonl] [bench-<t>.tsv]
Files with a "# NOTE" second line are discarded runs and are refused.
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"


def load(name):
    lines = (RESULTS / name).read_text().splitlines()
    if len(lines) > 1 and lines[1].startswith("# NOTE"):
        raise SystemExit(f"{name} is a discarded run: {lines[1]}")
    if not lines[0].startswith("# "):
        raise SystemExit(f"{name} has no stamp line")
    return lines


def plan_verdict(d, filtered=False):
    drift = [x for x in d["drift"] if not (filtered and x.get("computed_only"))]
    if d["mode"] == "normal":
        hits = [c["address"].removeprefix("digitalocean_") for c in d["changes"]]
        return ("yes: " + ", ".join(hits)) if d["exit"] == 2 else f"no (exit {d['exit']})"
    if not drift:
        return f"no (exit {d['exit']})" if not filtered else "no"
    return "yes: " + ", ".join(f"{x['address'].removeprefix('digitalocean_')} ({','.join(x['attrs'])})"
                               for x in drift)


def matrix(names):
    """names: one file, or several joined with commas (a round split over two files)."""
    rows = defaultdict(list)
    noise = []
    entries = []
    for name in names.split(","):
        lines = load(name)
        print(f"## Matrix ({name})\n\n{lines[0]}\n")
        entries += lines[1:]
    for ln in entries:
        r = json.loads(ln)
        if r["event"] == "scenario":
            rows[r["scenario"]].append(r)
        elif r["event"] == "revert":
            ro = r["refresh_only_after_apply"]
            noise.append((r["scenario"], ro["exit"], [(x["address"], x["attrs"]) for x in ro["drift"]]))
    print("| Scenario | refresh-only plan | same, computed-only drift dropped | normal plan | tofu refresh-only | inventory | rounds agree |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for scen, runs in rows.items():
        cells = []
        for r in runs:
            tf_ro, tf_n, tofu_ro, inv = r["detectors"]
            i = [f"unmanaged {u['type']} ({u['why']})" for u in inv["unmanaged"]] + \
                [f"missing {m['type']}" for m in inv["missing"]]
            cells.append((plan_verdict(tf_ro), plan_verdict(tf_ro, True), plan_verdict(tf_n),
                          plan_verdict(tofu_ro), "yes: " + "; ".join(i) if i else "no"))
        same = all(c == cells[0] for c in cells)
        print(f"| {scen} | " + " | ".join(cells[0]) + f" | {'yes' if same else 'NO'} ({len(cells)}) |")
        if not same:
            for c in cells[1:]:
                print(f"| {scen} (other round) | " + " | ".join(c) + " | |")
    print("\nrefresh-only plan right after each revert apply (before apply -refresh-only settles it):\n")
    for scen, code, drift in noise:
        print(f"- {scen}: exit {code} {drift if drift else ''}")
    print()


def watch(name):
    lines = load(name)
    print(f"## Time to detect ({name})\n\n{lines[0]}\n")
    rows = [json.loads(ln) for ln in lines[1:]]
    injects = [r for r in rows if r["kind"] == "inject"]
    signal = {"firewall-rule-added": ("plan", "digitalocean_firewall.web"),
              "dns-hotfix": ("plan", "digitalocean_record.app"),
              "tag-removed": ("plan", "digitalocean_droplet.web"),
              "record-created": ("inventory", "record"),
              "firewall-created": ("inventory", "firewall"),
              "droplet-created-untagged": (None, None)}
    print("| Scenario | injected at | detected by | detected at | time to detect |")
    print("| --- | --- | --- | --- | --- |")
    for inj in injects:
        kind, key = signal[inj["scenario"]]
        hit = None
        for r in rows:
            if r["kind"] != kind or r["t_start"] < inj["t_end"]:
                continue
            if kind == "plan" and key in r["drift"]:
                hit = r
            elif kind == "inventory" and any(u["type"] == key for u in r["unmanaged"]):
                hit = r
            if hit:
                break
        if hit:
            print(f"| {inj['scenario']} | {inj['t_end']} s | {kind} run at {hit['t_start']} s | {hit['t_end']} s | "
                  f"{round(hit['t_end'] - inj['t_end'], 1)} s |")
        else:
            print(f"| {inj['scenario']} | {inj['t_end']} s | nothing | | never (within the run) |")
    plans = [r for r in rows if r["kind"] == "plan"]
    invs = [r for r in rows if r["kind"] == "inventory"]
    print(f"\nplan runs: {len(plans)}, median {statistics.median(r['seconds'] for r in plans)} s; "
          f"inventory runs: {len(invs)}, median {statistics.median(r['seconds'] for r in invs)} s, "
          f"{sum(r['api_requests'] for r in invs)} requests in total\n")
    lastplan = plans[-1]
    print(f"last plan drift: {lastplan['drift']}")
    print(f"last inventory: {[u['why'] for u in invs[-1]['unmanaged']]}\n")


def bench(name):
    lines = load(name)
    print(f"## Detector cost ({name})\n\n{lines[0]}\n")
    by = defaultdict(list)
    logged = {}
    for ln in lines[2:]:
        det, run, sec, found, req = ln.split("\t")
        if run == "logged":
            logged[det] = req
        else:
            by[det].append(float(sec))
    print("| Detector | median | min | max | runs | API requests per run |")
    print("| --- | --- | --- | --- | --- | --- |")
    for det, s in by.items():
        print(f"| {det} | {round(statistics.median(s), 2)} s | {min(s)} s | {max(s)} s | {len(s)} | {logged.get(det, '')} |")
    print()


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        {"matrix": matrix, "watch": watch, "bench": bench}[arg.split("-")[0]](arg)
