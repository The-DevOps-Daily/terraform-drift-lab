#!/usr/bin/env bash
# Delete everything: resources created outside Terraform first, then the stack.
set -euo pipefail
cd "$(dirname "$0")/.."
TF=${TF:-terraform}
python3 scripts/cleanup_outside.py
$TF destroy -auto-approve -input=false -no-color | tail -2
echo "destroyed at $(date -u +%FT%TZ)"
