#!/usr/bin/env python3
"""Propose a new corpus entry from LexML URN/URL — human review required before merge."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.lexml_fetch_service import fetch_lexml_by_urn  # noqa: E402

URN_PATTERN = re.compile(r"urn:lex:[^\s\"']+", re.IGNORECASE)


def _extract_urn(raw: str) -> str:
    text = raw.strip()
    match = URN_PATTERN.search(text)
    if match:
        return match.group(0)
    if text.startswith("http"):
        # Best-effort: LexML URLs often contain urn after /urn/
        if "/urn/" in text:
            return text.split("/urn/", 1)[1].split("?")[0].strip("/")
    return text


def build_proposal(urn_or_url: str) -> dict:
    urn = _extract_urn(urn_or_url)
    fetched = fetch_lexml_by_urn(urn)
    slug = re.sub(r"[^a-z0-9]+", "-", urn.split(":")[-1].lower())[:48]
    title_pt = (fetched.get("text_pt") or urn)[:120]
    return {
        "proposed_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending_human_review",
        "id": f"proposed-{slug}",
        "source": "lexml",
        "urn": urn,
        "url": fetched.get("url") or f"https://www.lexml.gov.br/urn/{urn}",
        "title_pt": title_pt,
        "title_zh": "",
        "dimension": "",
        "tags": [],
        "checklist_codes": [],
        "text_pt": (fetched.get("text_pt") or "")[:1200],
        "text_zh": "",
        "fetch_status": fetched.get("status"),
        "fetch_message": fetched.get("message"),
        "note": "Edit dimension/tags/checklist_codes/title_zh before merging into brazil_legal_corpus.json",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Propose corpus entry from LexML URN (no auto-merge)")
    parser.add_argument("urn_or_url", help="LexML URN or URL")
    parser.add_argument(
        "-o",
        "--output",
        default=str(REPO_ROOT / "proposed_entry.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    proposal = build_proposal(args.urn_or_url)
    out_path = Path(args.output)
    out_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote proposal to {out_path} (fetch_status={proposal.get('fetch_status')})")
    if proposal.get("fetch_status") != "ok":
        print(f"Warning: {proposal.get('fetch_message')}", file=sys.stderr)


if __name__ == "__main__":
    main()
