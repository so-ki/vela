#!/usr/bin/env python3
"""Clean HTML/JS pollution from brazil_legal_corpus.json text_pt fields."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.corpus_text_cleaner import clean_text_pt, is_polluted

CORPUS_PATH = Path(__file__).resolve().parents[1] / "backend/app/data/brazil_legal_corpus.json"


def main() -> None:
    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)

    cleaned = 0
    for doc in corpus.get("sources") or []:
        raw = doc.get("text_pt_raw") or doc.get("text_pt") or ""
        if not raw:
            continue
        if not is_polluted(raw) and not doc.get("text_pt_raw"):
            doc["text_pt_clean"] = raw[:1200]
            doc["text_pt"] = doc["text_pt_clean"]
            continue
        if "text_pt_raw" not in doc and is_polluted(raw):
            doc["text_pt_raw"] = raw
        doc["text_pt_clean"] = clean_text_pt(
            raw,
            title_pt=doc.get("title_pt") or "",
            text_zh=doc.get("text_zh") or "",
        )
        doc["text_pt"] = doc["text_pt_clean"]
        cleaned += 1

    parts = str(corpus.get("version", "1.6")).split(".")
    if len(parts) >= 2 and parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]) + 1)
    corpus["version"] = ".".join(parts)
    corpus["cleaning_note"] = "text_pt HTML stripped; display uses text_pt_clean + text_zh summary"

    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Cleaned {cleaned} documents; corpus v{corpus['version']}; total {len(corpus.get('sources') or [])}")


if __name__ == "__main__":
    main()
