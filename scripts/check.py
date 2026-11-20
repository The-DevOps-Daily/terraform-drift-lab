#!/usr/bin/env python3
"""The scheduled drift check: one refresh-only plan plus one inventory diff.

Exit 0: nothing found. Exit 2: drift found (report on stdout). Exit 1: the check
itself broke (bad credentials, backend, provider error), which must fail the job.
Drift where only provider-computed attributes moved (a tag's droplets_count) is
listed but does not set exit 2.
"""
import sys

from common import TF, plan
import inventory


def main():
    p = plan(TF, refresh_only=True)
    if p["exit"] == 1:
        print(p.get("error", "plan failed"))
        return 1
    real = [d for d in p["drift"] if not d["computed_only"]]
    noise = [d for d in p["drift"] if d["computed_only"]]
    inv = inventory.scan()
    for d in real:
        print(f"DRIFT     {d['address']}: {', '.join(d['attrs']) or ', '.join(d['actions'])}")
    for u in inv["unmanaged"]:
        print(f"UNMANAGED {u['type']} {u['id']} ({u['why']})")
    for m in inv["missing"]:
        print(f"MISSING   {m['type']} {m['id']}")
    for d in noise:
        print(f"ignored   {d['address']}: computed only ({', '.join(d['attrs'])})")
    found = real or inv["unmanaged"] or inv["missing"]
    print(f"plan {p['seconds']} s, inventory {inv['seconds']} s, {inv['api_requests']} inventory requests")
    return 2 if found else 0


if __name__ == "__main__":
    sys.exit(main())
