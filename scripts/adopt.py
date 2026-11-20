#!/usr/bin/env python3
"""Adopt resources made outside Terraform with import blocks and generated config.

1. Create a record, a firewall and a tagged droplet (plus a new tag on it) by hand.
2. Run inventory.py to find them.
3. For Terraform and OpenTofu, in a copy of the working directory: write one
   import block per unmanaged resource, run plan -generate-config-out, then plan
   again with the generated file and record what the plan would do.
Nothing is applied. Writes results/adopt-<time>/.
"""
import json
import re
import shutil
import subprocess
import time

from common import LAB, RESULTS, ROOT, TF, TOFU, ZONE, doctl, stamp, tag
import cleanup_outside
import inventory
from scenarios import ctx, droplet_create, remember

TYPES = {"droplet": "digitalocean_droplet", "firewall": "digitalocean_firewall",
         "record": "digitalocean_record", "tag": "digitalocean_tag"}


def import_id(item):
    return f"{ZONE},{item['id']}" if item["type"] == "record" else item["id"]


def run(args, cwd):
    t0 = time.monotonic()
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return p, round(time.monotonic() - t0, 2)


def adopt(binary, found, outdir):
    name = binary.split("/")[-1]
    d = LAB / f"adopt-{name}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    for f in ("main.tf", "terraform.tfvars", "terraform.tfstate"):
        shutil.copy(ROOT / f, d / f)
    blocks = []
    for i, item in enumerate(found):
        if item["type"] not in TYPES:
            continue
        blocks.append(f'import {{\n  to = {TYPES[item["type"]]}.adopted_{i}\n  id = "{import_id(item)}"\n}}\n')
    (d / "imports.tf").write_text("\n".join(blocks))
    subprocess.run([binary, "init", "-input=false", "-no-color"], cwd=d, check=True, capture_output=True)
    gen, gen_s = run([binary, "plan", "-lock=false", "-no-color", "-input=false",
                      "-generate-config-out=generated.tf"], d)
    res = {"tool": name, "imports": len(blocks), "generate_exit": gen.returncode, "generate_seconds": gen_s}
    (outdir / f"{name}-generate.txt").write_text(gen.stdout + gen.stderr)
    if (d / "generated.tf").exists():
        shutil.copy(d / "generated.tf", outdir / f"{name}-generated.tf")
        second, s = run([binary, "plan", "-detailed-exitcode", "-lock=false", "-no-color", "-input=false",
                         "-out=adopt.bin"], d)
        res.update({"second_plan_exit": second.returncode, "second_plan_seconds": s})
        (outdir / f"{name}-second-plan.txt").write_text(second.stdout + second.stderr)
        if second.returncode == 1 and re.search(r'^\s*tag\s*=\s*""\s*$', (d / "generated.tf").read_text(), re.M):
            # OpenTofu writes tag = "" for a record without a CAA tag, which fails validation.
            # The one manual edit we allow: delete that line and plan again.
            fixed = re.sub(r'^\s*tag\s*=\s*""\s*\n', "", (d / "generated.tf").read_text(), flags=re.M)
            (d / "generated.tf").write_text(fixed)
            second, s = run([binary, "plan", "-detailed-exitcode", "-lock=false", "-no-color", "-input=false",
                             "-out=adopt.bin"], d)
            res.update({"fixed": 'deleted tag = "" lines', "after_fix_plan_exit": second.returncode,
                        "after_fix_plan_seconds": s})
            (outdir / f"{name}-after-fix-plan.txt").write_text(second.stdout + second.stderr)
        if second.returncode in (0, 2):
            show = json.loads(subprocess.run([binary, "show", "-json", "adopt.bin"], cwd=d,
                                             capture_output=True, text=True, check=True).stdout)
            res["changes"] = [{"address": c["address"], "actions": c["change"]["actions"],
                               "importing": "importing" in c["change"]}
                              for c in show.get("resource_changes", [])
                              if c["change"]["actions"] != ["no-op"] or "importing" in c["change"]]
    return res


def main():
    out = RESULTS / f"adopt-{tag()}"
    out.mkdir(parents=True)
    log = {"stamp": stamp("adopt.py")}
    c = ctx()
    r = doctl("compute", "domain", "records", "create", ZONE, "--record-type", "A", "--record-name", "debug",
              "--record-data", "198.51.100.8", "--record-ttl", "60")[0]
    remember("record", r["id"], "debug")
    fw = doctl("compute", "firewall", "create", "--name", "dl-hotfix-8080",
               "--inbound-rules", "protocol:tcp,ports:8080,address:0.0.0.0/0,address:::/0",
               "--droplet-ids", c["droplet"])[0]
    remember("firewall", fw["id"], "dl-hotfix-8080")
    doctl("compute", "tag", "create", "dl-owner-oncall")
    remember("tag", "dl-owner-oncall", "dl-owner-oncall")
    droplet_create("dl-web-debug", ["dl-web", "dl-owner-oncall"])
    time.sleep(5)
    inv = inventory.scan()
    log["inventory"] = inv
    try:
        log["results"] = [adopt(TF, inv["unmanaged"], out), adopt(TOFU, inv["unmanaged"], out)]
    finally:
        cleanup_outside.main()
    (out / "adopt.json").write_text(json.dumps(log, indent=2))
    print(json.dumps(log["results"], indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
