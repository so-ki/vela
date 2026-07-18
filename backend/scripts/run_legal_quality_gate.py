#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.legal_quality_eval import evaluate_legal_quality


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("controlled-pilot", "general-availability"), default="controlled-pilot")
    args = parser.parse_args()
    report = evaluate_legal_quality()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    key = "controlled_pilot_passed" if args.target == "controlled-pilot" else "general_availability_passed"
    return 0 if report[key] else 1


if __name__ == "__main__":
    raise SystemExit(main())
