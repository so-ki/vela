#!/usr/bin/env python3
"""Initialize database and seed demo user."""

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
    seed_script = BACKEND_DIR / "scripts" / "seed_demo_user.py"
    result = subprocess.run([sys.executable, str(seed_script)], cwd=BACKEND_DIR)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
