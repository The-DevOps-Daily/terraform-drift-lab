#!/usr/bin/env python3
"""How long after a backups action does the droplet API, and so the plan, show it?

The DigitalOcean provider reads `backups` from the droplet's `features` list.
This script turns backups on (or off) with doctl, then polls the droplet every
POLL seconds until `features` agrees with the action, for at most LIMIT seconds.
At each poll it records whether the backup policy endpoint already agrees.

Usage: backups_lag.py on|off|watch-off [reps]
  watch-off only polls, for a disable that already happened.
Writes results/backups-lag-<time>.jsonl.
"""
import sys
import time

from common import RESULTS, append_jsonl, doctl, now, stamp, tag
from scenarios import ctx

POLL = 15
LIMIT = 45 * 60


def features(did):
    return doctl("compute", "droplet", "get", did)[0]["features"]


def policy_enabled(did):
    try:
        return bool(doctl("compute", "droplet", "backup-policies", "get", did)[0].get("backup_enabled", False))
    except (RuntimeError, IndexError, KeyError):
        return None


def wait_for(did, want, out, label, t0):
    while time.monotonic() - t0 < LIMIT:
        f = features(did)
        has = "backups" in f
        append_jsonl(out, {"label": label, "t": round(time.monotonic() - t0, 1), "at": now(),
                           "features_has_backups": has, "policy_enabled": policy_enabled(did)})
        if has == want:
            return round(time.monotonic() - t0, 1)
        time.sleep(POLL)
    return None


def main():
    mode = sys.argv[1]
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    did = ctx()["droplet"]
    out = RESULTS / f"backups-lag-{tag()}.jsonl"
    out.write_text(stamp("backups_lag.py") + f" mode={mode} reps={reps} poll={POLL}s\n")
    for rep in range(1, reps + 1):
        steps = {"on": [True], "off": [False], "watch-off": [None]}.get(mode) or [True, False]
        for want in steps:
            if want is None:
                acts = doctl("compute", "droplet", "actions", did)
                last = next(a for a in acts if a["type"] == "disable_backups")
                append_jsonl(out, {"label": "existing disable_backups", "action": last["id"],
                                   "completed_at": last["completed_at"]})
                t0 = time.monotonic()
                lag = wait_for(did, False, out, f"{rep}:watch-off", t0)
                append_jsonl(out, {"label": f"{rep}:watch-off", "result": "flipped" if lag else "timeout",
                                   "seconds_after_watch_start": lag, "at": now()})
                continue
            action = "enable-backups" if want else "disable-backups"
            t0 = time.monotonic()
            act = doctl("compute", "droplet-action", action, did, "--wait")[0]
            append_jsonl(out, {"label": f"{rep}:{action}", "action": act["id"], "status": act["status"],
                               "completed_at": act.get("completed_at"), "at": now()})
            lag = wait_for(did, want, out, f"{rep}:{action}", t0)
            append_jsonl(out, {"label": f"{rep}:{action}", "result": "flipped" if lag else "timeout",
                               "seconds_after_action_start": lag, "at": now()})
            print(f"{rep}:{action}: features flipped after {lag} s", flush=True)


if __name__ == "__main__":
    main()
