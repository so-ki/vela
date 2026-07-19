#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

python3 "$ROOT/scripts/release_safety.py" check-docker
python3 "$ROOT/scripts/check_competition_claims.py"

if [ "$#" -gt 0 ]; then
  python3 "$ROOT/scripts/release_safety.py" scan-package "$1"
fi
