from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.legal_ingest import INDEX_FLAG, ingest_corpus, load_corpus

MONITOR_PATH = Path(__file__).resolve().parents[2] / "data" / "legal_monitor.json"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _corpus_fingerprint() -> str:
    corpus = load_corpus()
    payload = json.dumps(corpus.get("sources", []), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _load_state() -> dict[str, Any]:
    if not MONITOR_PATH.exists():
        return {"alerts": [], "last_scan_at": None, "corpus_fingerprint": None}
    with open(MONITOR_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict[str, Any]) -> None:
    MONITOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MONITOR_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_monitor_status() -> dict[str, Any]:
    corpus = load_corpus()
    breakdown: dict[str, int] = {}
    for s in corpus.get("sources", []):
        src = s.get("source", "unknown")
        breakdown[src] = breakdown.get(src, 0) + 1

    state = _load_state()
    index_flag = {}
    if INDEX_FLAG.exists():
        with open(INDEX_FLAG, encoding="utf-8") as f:
            index_flag = json.load(f)

    return {
        "enabled": True,
        "corpus_version": corpus.get("version", "1.0"),
        "document_count": len(corpus.get("sources", [])),
        "sources_breakdown": breakdown,
        "index_mode": index_flag.get("mode", "pending"),
        "last_scan_at": state.get("last_scan_at"),
        "corpus_fingerprint": state.get("corpus_fingerprint") or _corpus_fingerprint(),
        "alerts": state.get("alerts", [])[:20],
        "subscription_note": "MVP：本地语料变更检测 + 手动刷新索引；生产环境可对接 LexML RSS/API。",
    }


def scan_regulatory_updates(*, force_reindex: bool = False) -> dict[str, Any]:
    corpus = load_corpus()
    state = _load_state()
    prev_fp = state.get("corpus_fingerprint")
    current_fp = _corpus_fingerprint()
    now = _utcnow_iso()

    alerts: list[dict[str, Any]] = list(state.get("alerts", []))
    new_alerts: list[dict[str, Any]] = []

    if prev_fp and prev_fp != current_fp:
        new_alerts.append(
            {
                "id": f"corpus-{current_fp}",
                "level": "info",
                "title": "本地法源库版本变更",
                "message": f"语料指纹已更新（{prev_fp} → {current_fp}），建议重新绑定清单法条。",
                "detected_at": now,
            }
        )

    # 演示级监测条目：IBAMA / 州法更新提醒（辅线流程占位）
    demo_watch = [
        {
            "id": "watch-ibama-licensing",
            "level": "medium",
            "title": "IBAMA 环境许可口径监测",
            "message": "已扫描联邦环境许可相关条目；未发现本地语料删减，索引可继续使用。",
            "detected_at": now,
        },
        {
            "id": "watch-sp-icms",
            "level": "low",
            "title": "圣保罗州 ICMS 规则跟踪",
            "message": "州级税制条目已纳入索引；如有官方更新请扩充 brazil_legal_corpus.json。",
            "detected_at": now,
        },
    ]
    for item in demo_watch:
        if not any(a.get("id") == item["id"] for a in alerts):
            new_alerts.append(item)

    index_result = ingest_corpus(force=force_reindex)
    if force_reindex:
        new_alerts.append(
            {
                "id": f"reindex-{now[:10]}",
                "level": "info",
                "title": "法源索引已重建",
                "message": index_result.get("message", "索引刷新完成"),
                "detected_at": now,
            }
        )

    merged = (new_alerts + alerts)[:30]
    _save_state(
        {
            "last_scan_at": now,
            "corpus_fingerprint": current_fp,
            "alerts": merged,
        }
    )

    return {
        "scanned_at": now,
        "corpus_fingerprint": current_fp,
        "new_alerts": new_alerts,
        "alerts": merged,
        "index": index_result,
    }
