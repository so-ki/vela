#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

python3 "$ROOT/scripts/release_safety.py" check-docker

if [ "$#" -gt 0 ]; then
  python3 "$ROOT/scripts/release_safety.py" scan-package "$1"
fi
