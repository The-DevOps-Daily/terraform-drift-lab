# terraform-drift-lab

Make real drift on DigitalOcean, detect it three ways, and measure what each way misses: a scheduled `terraform plan -refresh-only -detailed-exitcode`, a cloud inventory diff (the driftctl approach), and import blocks with generated config to adopt what the inventory finds.

```bash
export DIGITALOCEAN_TOKEN=...   # droplets, firewalls, tags, domains, projects, ssh keys: read and write
export ZONE=tf-drift-lab.yourdomain.com   # a zone name under a domain you control; never delegated
scripts/setup.sh                 # 1 droplet, 1 firewall, 2 tags, 1 SSH key, 1 zone + 3 records, 1 project
python3 scripts/matrix.py 2      # each of 12 drifts on its own, every detector, 2 rounds
python3 scripts/exposure.py      # remove the dl-web tag and try port 22 before and after
python3 scripts/bench.py 10      # time and API requests per detector on the clean lab
python3 scripts/adopt.py         # import blocks + -generate-config-out for what the inventory found
python3 scripts/check_demo.py    # one run of scripts/check.py, the scheduled check, before and after drift
python3 scripts/watch.py 23      # 60 min schedule: plan every 10 min, inventory every 2 min, 6 drifts at random times
scripts/teardown.sh              # delete everything, including what the scenarios made by hand
python3 scripts/summarize.py matrix-<t>.jsonl watch-<t>.jsonl bench-<t>.tsv
```

Needs Terraform (we used 1.17.2), OpenTofu (1.13.9), doctl (2.7.0) and Python 3.10+. The droplet is `s-1vcpu-512mb-10gb` ($0.00595 an hour); the scenarios create up to two more for a few minutes each. Everything else in the lab costs nothing.

Write-up: [Terraform drift detection, measured](https://devops-daily.com/posts/terraform-drift-detection-measured).

## What each script does

- `common.py`: runs plans with `-detailed-exitcode` and reads `resource_drift` and `resource_changes` from `show -json`. For each drifted resource it records the attributes that changed and whether all of them are computed-only in the provider schema (`terraform providers schema -json`). OpenTofu plans run in `.lab/tofu` against a fresh copy of the Terraform state.
- `inventory.py`: lists what exists around the lab and compares IDs with the state. It reports `unmanaged` (in DigitalOcean, not in state) and `missing` (in state, not in DigitalOcean). It does not compare attributes. Its scope starts from the state: records in the lab zone (minus SOA and NS), droplets in the lab project or with a managed tag, firewalls that target those droplets or tags, and tags on those droplets.
- `scenarios.py`: the 12 drifts, each made with doctl the way a person would make it.
- `matrix.py`: for each scenario, confirms the lab is clean, injects, waits 5 s, runs four detectors, then deletes what was made by hand, applies, records the refresh-only plan right after that apply, and runs `apply -refresh-only`.
- `check.py`: the scheduled check (refresh-only plan + inventory). Exit 0 clean, 2 drift, 1 broken. Drift on computed-only attributes is printed but does not set exit 2.
- `examples/drift-check.yml`: the shape of that check as a GitHub Actions job. We did not run it in Actions; `watch.py` ran the schedule.

Every result file starts with a stamp line: script hash, tool versions, provider version, zone, start time. Predictions were committed before the measured matrix (`results/predictions-matrix.md`). Discarded runs are kept with a `# NOTE` second line that says what was wrong; `summarize.py` refuses them.

## Results

Terraform 1.17.2, OpenTofu 1.13.9, provider digitalocean 2.108.0, doctl 2.7.0, lon1, 2026-11-20.

### What each detector caught

`matrix-20261120T115337Z.jsonl` (round 1, and round 2 up to `record-deleted`) plus `matrix-20261120T121620Z.jsonl` (the rest of round 2; the first file stopped when the backups flag lag below kept the baseline dirty). Each drift alone, detectors run 5 s after the change. The verdicts were the same in both rounds; `backups-enabled` ran in round 1 only.

| Scenario | refresh-only plan (Terraform = OpenTofu) | normal plan | inventory.py |
| --- | --- | --- | --- |
| firewall-rule-added | yes (`inbound_rule`) | yes | no |
| dns-hotfix | yes (`ttl`, `value`) | yes | no |
| tag-removed | yes (droplet `tags`) | yes | no |
| tag-added | yes (droplet `tags`) | yes | yes, unmanaged tag |
| record-deleted | yes | yes | yes, missing |
| record-created | no | no | yes, unmanaged |
| firewall-created | no | no | yes, unmanaged |
| droplet-created-tagged | only via the tag's `droplets_count` | no | yes, unmanaged |
| droplet-created-untagged | no | no | no (outside the scope) |
| backups-enabled | no (the API showed it minutes later) | no | no |
| project-moved | yes (`resources`) | yes | no |
| firewall-deleted | yes | yes | yes, missing |

Plan: 7 of 12 (8 counting the counter). Inventory: 6 of 12. Three overlap (tag-added, record-deleted, firewall-deleted), so either: 10 of 12. The four detectors run one after the other after the 5 s wait, about 10 s in all, the inventory last. In round 2 the `record-deleted` plans also show the backups change left over from round 1.

After 5 of 23 revert applies, the next refresh-only plan exited 2 with no drift: tag counters (2), firewall `status`/`pending_changes` (1), firewall `droplet_ids` (2). Dropping drift where every changed attribute is computed-only in the provider schema removes the first two kinds, not the third.

### Removing the tag opens the droplet

`exposure-20261120T122350Z.json`: with the firewall in place, port 22 timed out from another server (3 of 3). 30 s after `doctl compute droplet untag ... dl-web`, it returned `SSH-2.0-OpenSSH_9.6p1`. The plan showed an update to the droplet's `tags`; the firewall resource showed only `status` and `pending_changes`. After the revert apply: 3 of 3 timeouts again.

### Detector cost

`bench-20261120T122351Z.tsv`, 10 runs each on the clean lab (10 resources):

| Detector | median | min | max | API requests |
| --- | --- | --- | --- | --- |
| terraform plan -refresh-only | 2.30 s | 2.06 s | 2.64 s | 11 |
| terraform plan | 2.20 s | 1.96 s | 2.88 s | 11 |
| tofu plan -refresh-only | 2.40 s | 2.02 s | 2.63 s | 11 |
| inventory.py | 3.59 s | 3.19 s | 3.96 s | 9 |

### Adopting with import blocks

`adopt-20261120T133020Z/`: four resources made by hand (record, firewall, tag, tagged droplet), found by `inventory.py`, one `import` block each, `plan -generate-config-out`, then a second plan with the generated file. Nothing applied.

- Terraform: config for all four; second plan `4 to import, 0 to add, 0 to change, 0 to destroy`, exit 2 (a pending import counts as a change).
- OpenTofu: wrote `tag = ""` for the A record, which fails the provider's validation (`expected tag to be one of [issue issuewild iodef]`). After deleting that line: `4 to import, 0 to add, 0 to change, 0 to destroy`.

Earlier attempts: `adopt-20261120T121100Z/` was confounded by the backups flag (see its `NOTE.txt`); `adopt-20261120T122907Z/` is clean but ran an older `adopt.py` without the one-line fix step, so its OpenTofu side stops at the error. The default VPC UUID in the generated droplet config is redacted in the committed files.

### The scheduled check

`check-demo-20261120T122801Z.txt`: `check.py` exits 0 on the clean lab, then 2 after three drifts, listing the firewall rule as DRIFT, the record and the droplet as UNMANAGED, and the tag counter as ignored.

### Time to detect

`watch-20261120T123001Z.jsonl`, seed 23: refresh-only plan every 10 min, inventory every 2 min, 60 min, six drifts at random times, none reverted.

| Drift | landed at | caught by | time to detect |
| --- | --- | --- | --- |
| record-created | 443.8 s | inventory | 40.1 s |
| dns-hotfix | 625.5 s | plan | 578.2 s |
| droplet-created-untagged | 746.0 s | nothing | not within the hour |
| firewall-created | 1307.3 s | inventory | 16.9 s |
| firewall-rule-added | 1368.3 s | plan | 435.4 s |
| tag-removed | 1619.0 s | plan | 184.7 s |

"Landed at" is when the doctl call returned. The plan at 600 s flagged `digitalocean_firewall.web` before any firewall change (`watch.py` records addresses only, so the attribute is unknown) and kept flagging it, so the real rule change at 1368 s appeared under an address that was already on the list. 7 plans (median 3.19 s), 31 inventory runs (median 3.91 s, 279 requests).

### The backups flag lags

The provider reads `backups` from the droplet's `features` list (see SOURCES.md). `backups-lag-20261120T133125Z.jsonl`, polling every 15 s after each doctl action:

| Rep | Action | `features` agreed after | backup policy endpoint |
| --- | --- | --- | --- |
| 1 | enable | 402.5 s | agreed at every poll |
| 1 | disable | 601.3 s | agreed at every poll |
| 2 | enable | 617.1 s | agreed at every poll |
| 2 | disable | 599.8 s | agreed at every poll |

In the matrix, the round 1 `enable_backups` completed at 12:00:57 and plans first showed it between about 12:05:08 and 12:05:28. `backups-lag-20261120T121055Z.jsonl` only watched an earlier disable that was already in progress (several disable actions had been sent), so it gives no clean number.

## Cost

The lab ran from 11:43 to 14:09 UTC on 2026-11-20: one `s-1vcpu-512mb-10gb` droplet the whole time ($0.00595 an hour), ten droplets made by the scenarios (most for a few minutes, one for 48), and under an hour of droplet backups in total. DigitalOcean bills droplets per second with a minimum of 60 seconds or $0.01, whichever is higher, so the ten extra droplets cost at least $0.10 and the main one about $0.014: roughly $0.12, plus the backups. `teardown.sh` destroyed all ten managed resources and the scenario leftovers; nothing named `dl-` was left in the account.
