#!/usr/bin/env python3
"""Inject three drifts, run check.py once, record its output, put the lab back.

Writes results/check-demo-<time>.txt.
"""
import subprocess
import sys
import time

from common import RESULTS, apply, stamp, tag
import cleanup_outside
from scenarios import SCENARIOS, ctx

NAMES = ["firewall-rule-added", "record-created", "droplet-created-tagged"]


def main():
    out = RESULTS / f"check-demo-{tag()}.txt"
    text = stamp("check_demo.py") + f" scenarios={','.join(NAMES)}\n"
    first = subprocess.run([sys.executable, "scripts/check.py"], capture_output=True, text=True)
    text += f"$ python3 scripts/check.py   # before\n{first.stdout}exit {first.returncode}\n\n"
    for n in NAMES:
        SCENARIOS[n](ctx())
    time.sleep(5)
    p = subprocess.run([sys.executable, "scripts/check.py"], capture_output=True, text=True)
    text += f"$ python3 scripts/check.py   # after {', '.join(NAMES)}\n{p.stdout}{p.stderr}exit {p.returncode}\n"
    out.write_text(text)
    print(text)
    cleanup_outside.main()
    apply()
    apply(refresh_only=True)


if __name__ == "__main__":
    main()
