# Predictions for matrix.py, written before the first measured run (2026-11-20)

Detectors: P = terraform plan -refresh-only, N = normal plan, T = tofu plan -refresh-only, I = inventory.py

| Scenario | P / N / T | I | Why we expect it |
| --- | --- | --- | --- |
| firewall-rule-added | yes | no | the firewall resource reads its full rule set; inventory compares IDs only |
| dns-hotfix | yes | no | record value and TTL are refreshed |
| tag-removed | yes (droplet tags) | no | droplet resource tracks its tags; the firewall still targets the tag, so the firewall itself shows nothing |
| tag-added | yes (droplet tags) | yes (unmanaged tag) | |
| record-deleted | yes | yes (missing) | |
| record-created | no | yes | no resource owns the new record |
| firewall-created | no | yes | the droplet resource does not track firewalls |
| droplet-created-tagged | no | yes | not in state; found through the dl-web tag |
| droplet-created-untagged | no | no | outside the inventory scope and not in state: nothing sees it |
| backups-enabled | yes | no | backups is a droplet argument |
| project-moved | yes | no | the project resource lists its resources |
| firewall-deleted | yes | yes (missing) | |

Noise seen once before writing this file: right after the first apply, plan -refresh-only exited 2 with
drift on both tags (droplets_count 0 -> 1). We expect that again after every revert apply that tags,
untags or deletes a droplet.
