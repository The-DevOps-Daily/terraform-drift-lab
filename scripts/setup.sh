#!/usr/bin/env bash
# Create the lab: one droplet, a firewall, two tags, an SSH key, a DNS zone with
# three records, and a project. About $0.006 per hour while the droplet exists.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ZONE:?set ZONE to a zone name under a domain you control, e.g. tf-drift-lab.example.com}"
: "${DIGITALOCEAN_TOKEN:?set DIGITALOCEAN_TOKEN}"
TF=${TF:-terraform}
mkdir -p .lab
[ -f .lab/id_ed25519 ] || ssh-keygen -q -t ed25519 -N '' -C drift-lab -f .lab/id_ed25519
cat > terraform.tfvars <<VARS
zone           = "$ZONE"
ssh_public_key = "$(cat .lab/id_ed25519.pub)"
VARS
$TF init -input=false -no-color > /dev/null
start=$(date +%s)
$TF apply -auto-approve -input=false -no-color | tail -3
echo "setup took $(( $(date +%s) - start ))s at $(date -u +%FT%TZ)"
date -u +%FT%TZ > .lab/created-at
