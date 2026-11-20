#!/usr/bin/env python3
"""Time each detector on the clean lab and count its API requests.

Usage: bench.py [runs]   (default 10, interleaved, 3 s apart)
Writes results/bench-<time>.tsv. Timed runs have no debug log; one extra
logged run per detector counts the requests the provider (or inventory.py) sent.
"""
import statistics
import sys
import time

from common import RESULTS, TF, TOFU, plan, stamp, tag
import inventory

DETECTORS = {
    "terraform plan -refresh-only": lambda log=False: plan(TF, True, log),
    "terraform plan": lambda log=False: plan(TF, False, log),
    "tofu plan -refresh-only": lambda log=False: plan(TOFU, True, log),
    "inventory.py": lambda log=False: inventory.scan(),
}


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    out = RESULTS / f"bench-{tag()}.tsv"
    rows = []
    with open(out, "w") as f:
        f.write(stamp("bench.py") + f" runs={runs}\n")
        f.write("detector\trun\tseconds\texit_or_findings\tapi_requests\n")
        for i in range(1, runs + 1):
            for name, det in DETECTORS.items():
                r = det()
                found = r.get("exit", len(r.get("unmanaged", [])) + len(r.get("missing", [])))
                f.write(f"{name}\t{i}\t{r['seconds']}\t{found}\t{r.get('api_requests', '')}\n")
                rows.append((name, r["seconds"]))
                time.sleep(3)
        for name, det in DETECTORS.items():
            r = det(True)
            f.write(f"{name}\tlogged\t{r['seconds']}\t{r.get('exit', '')}\t{r.get('api_requests', '')}\n")
    for name in DETECTORS:
        s = sorted(x for n, x in rows if n == name)
        print(f"{name}: median {statistics.median(s)} s, min {s[0]}, max {s[-1]} (n={len(s)})")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
