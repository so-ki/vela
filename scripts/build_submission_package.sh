#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT="${1:-${TMPDIR:-/tmp}/vela-capability-pack-mvp.zip}"

python3 "$ROOT/scripts/release_safety.py" check-docker
python3 "$ROOT/scripts/release_safety.py" build-package "$OUTPUT"
