"""Fetch official LexML text to backtrack/enrich corpus entries."""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import quote
from xml.etree import ElementTree

import httpx

from app.core.config import get_settings
from app.services.legal_ingest import load_corpus

LEXML_URN_API = "https://www.lexml.gov.br/urn"
LEXML_DOC_API = "https://www.lexml.gov.br/documento"
MAX_OFFICIAL_RESPONSE_BYTES = 1024 * 1024


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def fetch_lexml_by_urn(urn: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """Resolve URN via LexML public endpoint; returns best-effort official excerpt."""
    if get_settings().is_production:
        return {
            "status": "disabled",
            "message": "生产受控试点禁用实时法源外发，请使用版本化本地语料并人工核验",
        }
    urn = (urn or "").strip()
    if not urn or len(urn) > 500:
        return {"status": "error", "message": "URN 为空"}

    encoded_urn = quote(urn, safe=":;,.+-")
    urls = [
        f"{LEXML_URN_API}/{encoded_urn}",
        f"{LEXML_DOC_API}?urn={encoded_urn}",
    ]
    last_error = ""
    with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        for url in urls:
            try:
                with client.stream(
                    "GET",
                    url,
                    headers={"Accept": "application/xml, text/xml, text/html"},
                ) as resp:
                    if resp.is_redirect:
                        last_error = "官方端点返回重定向，已拒绝跟随"
                        continue
                    if resp.status_code >= 400:
                        last_error = f"HTTP {resp.status_code}"
                        continue
                    declared = int(resp.headers.get("content-length") or 0)
                    if declared > MAX_OFFICIAL_RESPONSE_BYTES:
                        last_error = "官方响应超过 1MB 上限"
                        continue
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > MAX_OFFICIAL_RESPONSE_BYTES:
                            raise ValueError("官方响应超过 1MB 上限")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    body = raw.decode(resp.encoding or "utf-8", errors="replace")
                    content_type = resp.headers.get("content-type", "")
                    final_url = str(resp.url)
                if "xml" in content_type or body.strip().startswith("<"):
                    text = _extract_text_from_xml(body)
                else:
                    text = _strip_html(body)
                if len(text) < 40:
                    last_error = "返回内容过短"
                    continue
                return {
                    "status": "ok",
                    "urn": urn,
                    "url": final_url,
                    "text_pt": text[:12000],
                    "fetched_bytes": len(raw),
                }
            except Exception:
                last_error = "LexML 官方端点请求失败或响应不符合安全边界"

    return {"status": "error", "urn": urn, "message": last_error or "LexML 请求失败"}


def _extract_text_from_xml(xml_text: str) -> str:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return _strip_html(xml_text)
    chunks: list[str] = []
    for elem in root.iter():
        if elem.text and elem.text.strip():
            chunks.append(elem.text.strip())
        if elem.tail and elem.tail.strip():
            chunks.append(elem.tail.strip())
    return " ".join(chunks)


def enrich_corpus_document_from_lexml(doc_id: str, *, persist: bool = True) -> dict[str, Any]:
    """Backtrack corpus entry to LexML official text when URN is available."""
    corpus = load_corpus()
    doc = next((d for d in corpus.get("sources", []) if d.get("id") == doc_id), None)
    if not doc:
        return {"status": "error", "message": f"语料条目不存在: {doc_id}"}

    urn = (doc.get("urn") or "").strip()
    if not urn or doc.get("source") not in ("lexml", "stf", "stj"):
        return {
            "status": "skipped",
            "message": "仅支持含 URN 的 lexml/stf/stj 条目回溯",
            "doc_id": doc_id,
        }

    fetched = fetch_lexml_by_urn(urn)
    if fetched.get("status") != "ok":
        return {"status": "error", "doc_id": doc_id, **fetched}

    previous_len = len(doc.get("text_pt") or "")
    if persist:
        return {
            "status": "error",
            "doc_id": doc_id,
            "message": (
                "active corpus 为只读内容寻址制品；LexML 结果只能进入候选复核队列，"
                "不得原地覆盖"
            ),
        }

    return {
        "status": "ok",
        "doc_id": doc_id,
        "urn": urn,
        "previous_length": previous_len,
        "new_length": len(fetched["text_pt"]),
        "official_url": fetched.get("url"),
        "candidate": {
            "doc_id": doc_id,
            "urn": urn,
            "official_url": fetched.get("url"),
            "text_pt": fetched["text_pt"],
        },
        "message": "已读取 LexML 官方候选文本，尚未修改 active corpus",
    }
