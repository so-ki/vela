"""Official Brazil legal portal registry — LexML · Planalto · STF · gov.br (no API key)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx

from app.core.config import get_settings

PORTALS_PATH = Path(__file__).resolve().parents[1] / "data" / "brazil_official_portals.json"

# 各维度优先展示的官方法源（用于 portal_link 降级）
DIMENSION_PORTAL_ORDER: dict[str, list[str]] = {
    "labor": ["trabalho", "lexml", "planalto-legislacao", "previdencia"],
    "tax": ["receita-federal", "lexml", "planalto-legislacao"],
    "environment": ["ibama", "lexml", "planalto-legislacao"],
    "foreign_investment": ["lexml", "planalto-legislacao", "stf"],
    "industry_access": ["lexml", "planalto-legislacao", "stf"],
    "data_compliance": ["planalto-legislacao", "lexml", "stf"],
}


def load_official_portals() -> dict[str, Any]:
    with open(PORTALS_PATH, encoding="utf-8") as f:
        return json.load(f)


def list_portals(*, dimension: Optional[str] = None) -> list[dict[str, Any]]:
    data = load_official_portals()
    portals = list(data.get("portals") or [])
    if not dimension:
        return portals
    order = DIMENSION_PORTAL_ORDER.get(dimension, ["lexml", "planalto-legislacao", "stf"])
    by_id = {p["id"]: p for p in portals}
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pid in order:
        if pid in by_id and pid not in seen:
            ordered.append(by_id[pid])
            seen.add(pid)
    for p in portals:
        if p["id"] not in seen and dimension in (p.get("dimensions") or []):
            ordered.append(p)
            seen.add(p["id"])
    return ordered


def portal_search_url(portal: dict[str, Any], query: str) -> str:
    template = portal.get("search_url_template") or portal.get("url") or ""
    q = quote((query or "")[:200])
    if "{query}" in template:
        return template.format(query=q)
    return template


def build_portal_hits(
    query: str,
    dimension: str,
    item_code: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Generate official portal citation links when corpus/LexML live miss."""
    hits: list[dict[str, Any]] = []
    for portal in list_portals(dimension=dimension)[:limit]:
        url = portal_search_url(portal, query)
        hits.append(
            {
                "id": f"portal-{portal['id']}-{item_code}",
                "source": portal["id"],
                "source_label": portal.get("label_zh") or portal.get("label_pt", portal["id"]),
                "urn": "",
                "url": url,
                "title_pt": f"{portal.get('label_pt', '')} — {query[:60]}",
                "title_zh": f"{portal.get('label_zh', '')} · 官方检索入口",
                "excerpt_pt": portal.get("notes_zh", "")[:200],
                "excerpt_zh": "语料/LexML 未充分命中时，请通过官方法源门户人工核对具体法条或判决。",
                "match_score": 35.0 - len(hits) * 2,
                "requires_review": True,
                "citation_tier": "portal_link",
                "citation_tier_label": "官方法源门户（须律师核对）",
                "checklist_code": item_code,
                "connector": "brazil_official",
            }
        )
    return hits


def probe_official_endpoints(*, timeout: float = 12.0) -> list[dict[str, Any]]:
    """Health check for LexML / Planalto / STF / gov.br — used by connector status."""
    probes = [
        {"id": "lexml", "label": "LexML Brasil", "url": "https://www.lexml.gov.br/"},
        {
            "id": "lexml_urn_sample",
            "label": "LexML URN（LGPD 样例）",
            "url": "https://www.lexml.gov.br/urn/urn:lex:br:federal:lei:2018-08-14;13709",
        },
        {"id": "planalto", "label": "Planalto 立法", "url": "https://www4.planalto.gov.br/legislacao/"},
        {"id": "stf", "label": "STF", "url": "https://portal.stf.jus.br/"},
        {"id": "trabalho", "label": "劳动与就业部", "url": "https://www.gov.br/trabalho-e-emprego/pt-br"},
    ]
    if get_settings().is_production:
        return [
            {
                **item,
                "reachable": False,
                "probe_disabled": True,
                "error": "生产受控试点禁用实时外部探测",
            }
            for item in probes
        ]
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        for item in probes:
            row = {**item, "reachable": False}
            try:
                resp = client.head(item["url"])
                status_code = resp.status_code
                final_url = str(resp.url)
                if status_code >= 400:
                    with client.stream("GET", item["url"]) as streamed:
                        status_code = streamed.status_code
                        final_url = str(streamed.url)
                row["reachable"] = status_code < 400 and not 300 <= status_code < 400
                row["status_code"] = status_code
                row["final_url"] = final_url
            except Exception:
                row["error"] = "官方端点请求失败"
            results.append(row)
    return results
