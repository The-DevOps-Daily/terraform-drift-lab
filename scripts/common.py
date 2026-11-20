"""Shared helpers: run Terraform/OpenTofu plans, call the DigitalOcean API, stamp results."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / ".lab"  # gitignored: ssh key, plan files, the OpenTofu copy
RESULTS = ROOT / "results"
TF = os.environ.get("TF", "terraform")
TOFU = os.environ.get("TOFU", "tofu")
ZONE = os.environ["ZONE"]
TOKEN = os.environ["DIGITALOCEAN_TOKEN"]
API = "https://api.digitalocean.com/v2"
PROVIDER = "2.108.0"

os.environ.setdefault("DIGITALOCEAN_ACCESS_TOKEN", TOKEN)
os.environ["TF_VAR_zone"] = ZONE
os.environ["TF_IN_AUTOMATION"] = "1"
os.environ["TF_INPUT"] = "0"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tag():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def code_hash():
    h = hashlib.sha256()
    for p in [ROOT / "main.tf", *sorted((ROOT / "scripts").iterdir())]:
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


def version(binary):
    return subprocess.run([binary, "version"], capture_output=True, text=True).stdout.splitlines()[0]


def stamp(script):
    return (f"# {script} sha256={code_hash()} {version(TF)} / {version(TOFU)} "
            f"provider={PROVIDER} zone={ZONE} started={now()}")


class Api:
    """Minimal DigitalOcean API client that counts its own requests."""

    def __init__(self):
        self.requests = 0

    def call(self, method, path, body=None):
        self.requests += 1
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(API + path, data=data, method=method, headers={
            "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {}

    def get(self, path):
        return self.call("GET", path)

    def list(self, path, key):
        out, page = [], 1
        sep = "&" if "?" in path else "?"
        while True:
            status, body = self.get(f"{path}{sep}per_page=200&page={page}")
            if status != 200:
                raise RuntimeError(f"GET {path}: {status} {body}")
            out += body.get(key, [])
            if "next" not in body.get("links", {}).get("pages", {}):
                return out
            page += 1


def state(binary=TF, cwd=ROOT):
    out = subprocess.run([binary, "show", "-json"], cwd=cwd, capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    return data.get("values", {}).get("root_module", {}).get("resources", [])


def tofu_dir():
    """An OpenTofu working copy that plans against a copy of the Terraform state."""
    d = LAB / "tofu"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "main.tf", d / "main.tf")
    shutil.copy(ROOT / "terraform.tfvars", d / "terraform.tfvars")
    shutil.copy(ROOT / "terraform.tfstate", d / "terraform.tfstate")
    if not (d / ".terraform").exists():
        subprocess.run([TOFU, "init", "-input=false", "-no-color"], cwd=d, check=True, capture_output=True)
    return d


_SCHEMA = {}


def computed_only(rtype):
    """Attribute names of rtype that only the provider sets (computed, not optional or required)."""
    if not _SCHEMA:
        cache = LAB / "schema.json"
        if not cache.exists():
            cache.write_text(subprocess.run([TF, "providers", "schema", "-json"], cwd=ROOT,
                                            capture_output=True, text=True, check=True).stdout)
        for prov in json.loads(cache.read_text())["provider_schemas"].values():
            for t, sch in prov["resource_schemas"].items():
                _SCHEMA[t] = {n for n, a in sch["block"].get("attributes", {}).items()
                              if a.get("computed") and not a.get("optional") and not a.get("required")}
    return _SCHEMA.get(rtype, set())


def changed_attrs(change):
    before, after = change.get("before") or {}, change.get("after") or {}
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def plan(binary=TF, refresh_only=True, log_requests=False):
    """Run one plan with -detailed-exitcode and return what it reports.

    drift: resources the refresh found changed outside Terraform (resource_drift).
    changes: resources the plan would create, update, replace or delete.
    """
    cwd = tofu_dir() if binary == TOFU else ROOT
    planfile = LAB / f"plan-{Path(binary).name}.bin"
    args = [binary, "plan", "-detailed-exitcode", "-lock=false", "-no-color", "-input=false", f"-out={planfile}"]
    if refresh_only:
        args.append("-refresh-only")
    env = dict(os.environ)
    logfile = LAB / "tf-debug.log"
    if log_requests:
        env["TF_LOG"] = "DEBUG"
        env["TF_LOG_PATH"] = str(logfile)
        logfile.unlink(missing_ok=True)
    t0 = time.monotonic()
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    seconds = round(time.monotonic() - t0, 2)
    result = {"tool": Path(binary).name, "mode": "refresh-only" if refresh_only else "normal",
              "exit": p.returncode, "seconds": seconds, "drift": [], "changes": []}
    if p.returncode == 1:
        result["error"] = p.stderr.strip()[-600:]
        return result
    show = json.loads(subprocess.run([binary, "show", "-json", str(planfile)], cwd=cwd,
                                     capture_output=True, text=True, check=True).stdout)
    for d in show.get("resource_drift", []):
        attrs = changed_attrs(d["change"])
        result["drift"].append({"address": d["address"], "actions": d["change"]["actions"], "attrs": attrs,
                                "computed_only": bool(attrs) and set(attrs) <= computed_only(d["type"])})
    for c in show.get("resource_changes", []):
        if c["change"]["actions"] != ["no-op"]:
            result["changes"].append({"address": c["address"], "actions": c["change"]["actions"]})
    if log_requests:
        text = logfile.read_text(errors="replace")
        result["api_requests"] = len(re.findall(r"^(GET|POST|PUT|PATCH|DELETE) /v2/", text, re.M))
        logfile.unlink(missing_ok=True)
    return result


def doctl(*args):
    p = subprocess.run(["doctl", *args, "-o", "json"], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"doctl {' '.join(args)}: {p.stderr.strip()} {p.stdout.strip()[:400]}")
    return json.loads(p.stdout) if p.stdout.strip() else None


def apply(refresh_only=False):
    args = [TF, "apply", "-auto-approve", "-no-color", "-input=false"]
    if refresh_only:
        args.append("-refresh-only")
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stdout[-1500:] + p.stderr[-1500:])
    return p.stdout


def append_jsonl(path, obj):
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")
