"""Fetch official LexML text to backtrack/enrich corpus entries."""

from __future__ import annotations

import re
from typing import Any, Optional
from xml.etree import ElementTree

import httpx

from app.services.legal_ingest import CORPUS_PATH, load_corpus

LEXML_URN_API = "https://www.lexml.gov.br/urn"
LEXML_DOC_API = "https://www.lexml.gov.br/documento"


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def fetch_lexml_by_urn(urn: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """Resolve URN via LexML public endpoint; returns best-effort official excerpt."""
    urn = (urn or "").strip()
    if not urn:
        return {"status": "error", "message": "URN 为空"}

    urls = [
        f"{LEXML_URN_API}/{urn}",
        f"{LEXML_DOC_API}?urn={urn}",
    ]
    last_error = ""
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = client.get(url, headers={"Accept": "application/xml, text/xml, text/html, */*"})
                if resp.status_code >= 400:
                    last_error = f"HTTP {resp.status_code}"
                    continue
                content_type = resp.headers.get("content-type", "")
                body = resp.text
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
                    "url": str(resp.url),
                    "text_pt": text[:12000],
                    "fetched_bytes": len(body),
                }
            except Exception as exc:
                last_error = str(exc)[:200]

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
    import json

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
    doc["text_pt"] = fetched["text_pt"]
    doc["url"] = fetched.get("url") or doc.get("url", "")
    doc["lexml_synced_at"] = fetched.get("fetched_at")

    if persist:
        with open(CORPUS_PATH, "w", encoding="utf-8") as f:
            json.dump(corpus, f, ensure_ascii=False, indent=2)
            f.write("\n")

    return {
        "status": "ok",
        "doc_id": doc_id,
        "urn": urn,
        "previous_length": previous_len,
        "new_length": len(fetched["text_pt"]),
        "official_url": fetched.get("url"),
        "message": "已从 LexML 官方源更新 text_pt",
    }
