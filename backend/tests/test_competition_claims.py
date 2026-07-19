from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_finalist_surfaces_use_canonical_positioning_and_no_blocked_claims() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_competition_claims.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
