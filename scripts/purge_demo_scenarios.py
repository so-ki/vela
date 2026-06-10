#!/usr/bin/env python3
"""Permanently remove BYD / demo investigation scenarios from the local database."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.core.database import SessionLocal, init_db  # noqa: E402
from app.models.scenario import InvestigationScenario  # noqa: E402
from app.services.rule_engine import get_demo_scenario_template  # noqa: E402

DATA_DIR = BACKEND / "data"
MONITOR_PATH = DATA_DIR / "legal_monitor.json"

DEMO_NAME = get_demo_scenario_template()["project_name"]


def _is_demo_scenario(name: str) -> bool:
    if name == DEMO_NAME:
        return True
    return "（演示案例）" in name or "（演示）" in name


def _prune_monitor_subscriptions(deleted_ids: set[int]) -> int:
    if not MONITOR_PATH.exists() or not deleted_ids:
        return 0
    with open(MONITOR_PATH, encoding="utf-8") as f:
        data = json.load(f)
    removed = 0
    for key in ("subscriptions", "alerts"):
        items = data.get(key)
        if not isinstance(items, list):
            continue
        kept = []
        for item in items:
            sid = item.get("scenario_id")
            if isinstance(sid, int) and sid in deleted_ids:
                removed += 1
                continue
            kept.append(item)
        data[key] = kept
    with open(MONITOR_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return removed


def main() -> None:
    init_db()
    with SessionLocal() as db:
        rows = db.query(InvestigationScenario).order_by(InvestigationScenario.id).all()
        demo_rows = [s for s in rows if _is_demo_scenario(s.project_name)]
        if not demo_rows:
            print("No demo scenarios found.")
            return
        deleted_ids = {s.id for s in demo_rows}
        for s in demo_rows:
            print(f"DELETE #{s.id} · {s.project_name} · {s.status}")
            db.delete(s)
        db.commit()
    pruned = _prune_monitor_subscriptions(deleted_ids)
    print(f"Removed {len(deleted_ids)} demo scenario(s); pruned {pruned} monitor reference(s).")


if __name__ == "__main__":
    main()
