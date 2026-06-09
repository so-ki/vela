"""Regulatory feed watcher + policy diff (Claude for Legal regulatory-legal pattern)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.legal_monitor import compute_corpus_diff, _load_state, _save_state

# 官方 Reg Feed 订阅源 — LexML · Planalto · STF · gov.br（无需 API Key）
REG_FEED_SOURCES = [
    {
        "id": "planalto-legislacao",
        "label": "Planalto 总统府立法",
        "url": "http://www4.planalto.gov.br/legislacao/",
        "feed_type": "html",
        "dimensions": ["foreign_investment", "labor", "tax", "environment", "data_compliance"],
        "checklist_codes": [],
        "status": "watch",
    },
    {
        "id": "stf-portal",
        "label": "STF 联邦最高法院",
        "url": "http://www.stf.jus.br/",
        "feed_type": "html",
        "dimensions": ["foreign_investment", "labor", "tax", "environment"],
        "checklist_codes": [],
        "status": "watch",
    },
    {
        "id": "trabalho-govbr",
        "label": "劳动与就业部 gov.br",
        "url": "https://www.gov.br/trabalho-e-emprego/pt-br",
        "feed_type": "html",
        "dimensions": ["labor"],
        "checklist_codes": ["LAB-001", "LAB-002", "LAB-003"],
        "status": "watch",
    },
    {
        "id": "previdencia-govbr",
        "label": "社会保障部 gov.br",
        "url": "https://www.gov.br/previdencia/pt-br",
        "feed_type": "html",
        "dimensions": ["labor"],
        "checklist_codes": ["LAB-004"],
        "status": "watch",
    },
    {
        "id": "camex-resolucoes",
        "label": "CAMEX / GECEX 外贸决议",
        "url": "https://www.gov.br/mdic/pt-br/assuntos/camex/resolucoes",
        "feed_type": "html",
        "dimensions": ["tax", "industry_access"],
        "checklist_codes": ["TAX-004"],
        "status": "watch",
    },
    {
        "id": "ibama-noticias",
        "label": "IBAMA 环保法规与新闻",
        "url": "https://www.gov.br/ibama/pt-br/assuntos/noticias",
        "feed_type": "html_rss",
        "dimensions": ["environment"],
        "checklist_codes": ["ENV-001", "ENV-004"],
        "status": "watch",
    },
    {
        "id": "anpd-noticias",
        "label": "ANPD 数据保护动态",
        "url": "https://www.gov.br/anpd/pt-br/assuntos/noticias",
        "feed_type": "html_rss",
        "dimensions": ["data_compliance"],
        "checklist_codes": ["DAT-001", "DAT-002", "DAT-003"],
        "status": "watch",
    },
    {
        "id": "investsp-incentivos",
        "label": "InvestSP 圣保罗州税收激励",
        "url": "https://www.investe.sp.gov.br/por-que-sao-paulo/incentivos-fiscais/",
        "feed_type": "html",
        "dimensions": ["tax"],
        "checklist_codes": ["TAX-002", "IND-008"],
        "status": "watch",
    },
    {
        "id": "sefaz-sp-beneficios",
        "label": "Sefaz-SP ICMS 优惠法令清单",
        "url": "https://portal.fazenda.sp.gov.br/acessoinformacao/Paginas/Beneficios-Fiscais.aspx",
        "feed_type": "html",
        "dimensions": ["tax"],
        "checklist_codes": ["TAX-002"],
        "status": "watch",
    },
    {
        "id": "lexml-portal",
        "label": "LexML Brasil 联邦立法索引",
        "url": "https://www.lexml.gov.br/",
        "feed_type": "portal",
        "dimensions": ["foreign_investment", "labor", "tax", "environment"],
        "checklist_codes": [],
        "status": "watch",
    },
]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _probe_source(url: str, *, timeout: float = 12.0) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.head(url)
            if resp.status_code >= 400:
                resp = client.get(url)
            return {
                "reachable": resp.status_code < 400,
                "status_code": resp.status_code,
                "final_url": str(resp.url),
            }
    except Exception as exc:
        return {"reachable": False, "status_code": None, "error": str(exc)[:120]}


def get_reg_feed_status() -> dict[str, Any]:
    state = _load_state()
    last_diff = state.get("last_diff") or compute_corpus_diff(
        prev_snapshot=state.get("doc_snapshot") or None
    )
    return {
        "sources": REG_FEED_SOURCES,
        "last_checked_at": state.get("last_reg_feed_at"),
        "policy_diff": last_diff if last_diff.get("has_changes") else None,
        "affected_dimensions": _dimensions_from_diff(last_diff),
        "recent_items": (state.get("reg_feed_items") or [])[:10],
        "note": "扫描 LexML · Planalto · STF · gov.br 可达性 + 本地语料 Policy Diff；HTML 全文抓取为后续迭代。",
    }


def _dimensions_from_diff(diff: dict[str, Any]) -> list[str]:
    dims: set[str] = set()
    from app.services.legal_ingest import load_corpus

    by_id = {d["id"]: d for d in load_corpus().get("sources", []) if d.get("id")}
    for ch in diff.get("changed_documents") or []:
        doc = by_id.get(ch.get("id"), ch)
        dim = doc.get("dimension")
        if dim:
            dims.add(dim)
    for src in REG_FEED_SOURCES:
        for dim in src.get("dimensions") or []:
            if any(c in (diff.get("affected_checklist_codes") or []) for c in src.get("checklist_codes") or []):
                dims.add(dim)
    return sorted(dims)


def scan_reg_feed(*, force: bool = False) -> dict[str, Any]:
    """Poll reg sources (reachability) + merge with corpus policy diff."""
    state = _load_state()
    prev_snapshot = dict(state.get("doc_snapshot") or {})
    diff = compute_corpus_diff(prev_snapshot=prev_snapshot if prev_snapshot else None)
    now = _utcnow_iso()

    feed_items: list[dict[str, Any]] = []
    if diff.get("has_changes"):
        feed_items.append(
            {
                "id": f"policy-diff-{now[:10]}",
                "source_id": "local-corpus",
                "title": "法源语料 Policy Diff",
                "summary": (
                    f"{len(diff.get('changed_documents') or [])} 条语料变更，"
                    f"影响核查项 {', '.join((diff.get('affected_checklist_codes') or [])[:6])}"
                ),
                "affected_checklist_codes": diff.get("affected_checklist_codes") or [],
                "detected_at": now,
                "level": "medium",
            }
        )

    unreachable: list[str] = []
    for src in REG_FEED_SOURCES:
        probe = _probe_source(src["url"])
        level = "low" if probe.get("reachable") else "high"
        if not probe.get("reachable"):
            unreachable.append(src["id"])
        feed_items.append(
            {
                "id": f"{src['id']}-scan-{now[:19]}",
                "source_id": src["id"],
                "title": src["label"],
                "url": src["url"],
                "summary": (
                    f"源站可达（HTTP {probe.get('status_code')}）"
                    if probe.get("reachable")
                    else f"源站不可达：{probe.get('error') or probe.get('status_code')}"
                ),
                "affected_checklist_codes": src.get("checklist_codes") or [],
                "detected_at": now,
                "level": level,
                "reachable": bool(probe.get("reachable")),
            }
        )

    state["last_reg_feed_at"] = now
    state["reg_feed_items"] = (feed_items + list(state.get("reg_feed_items") or []))[:40]
    state["reg_feed_unreachable"] = unreachable
    if diff.get("has_changes"):
        state["last_diff"] = diff
    _save_state(state)

    return {
        "scanned_at": now,
        "feed_items": feed_items,
        "policy_diff": diff,
        "affected_dimensions": _dimensions_from_diff(diff),
        "unreachable_sources": unreachable,
    }
