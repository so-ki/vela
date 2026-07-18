"""实验④ 摄入 QA 抽样.

对含修订注记的法规文本（典型样本：Decreto 8.468/76 括号注记嵌正文），
把管线解析结果切块导出为比对工作表，供人工逐条比对后回填误差，
再由本脚本统计块级误差率。

判据先行（见 docs/experiments/README.md，2026-07-18 预登记）：
  块级解析误差率 <= 5% -> A 层可承诺"与来源快照逐块一致"；
  > 5% -> 承诺降级为"整体一致，块级定位仅供导航"，误差率写入技术诚实声明。

用法：
  # 第一步：从语料生成比对工作表（抽取含修订注记特征的条目）
  python scripts/experiment04_ingest_qa_sampling.py generate

  # 或：从官方整合全文在线抓取真实样本（ALESP 官方仓库）
  python scripts/experiment04_ingest_qa_sampling.py generate --from-official

  # 第二步：人工在 docs/experiments/results/exp04_worksheet.json 中
  #         为每块回填 "verdict": "ok" | "error" | "unsure"，并写 "note"

  # 第三步：统计误差率
  python scripts/experiment04_ingest_qa_sampling.py score
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "backend" / "app" / "data" / "brazil_legal_corpus.json"
RESULT_DIR = REPO_ROOT / "docs" / "experiments" / "results"
WORKSHEET = RESULT_DIR / "exp04_worksheet.json"

# 修订注记特征：葡语法规文本中嵌入的括号修订说明
REVISION_MARKERS = re.compile(
    r"\((?:Reda[cç][aã]o dada|Inclu[ií]d[oa]|Revogad[oa]|Renumerad[oa]|Vide|Alterad[oa])[^)]*\)",
    re.IGNORECASE,
)


# 官方整合全文源（ALESP 州议会法规仓库，公开、无版权限制）
OFFICIAL_SOURCES = [
    {
        "source_id": "alesp-decreto-8468-1976",
        "urn": "urn:lex:br;sao.paulo:estadual:decreto:1976-09-08;8468",
        "title": "Decreto 8.468/1976 (SP) — texto consolidado ALESP",
        "url": "https://www.al.sp.gov.br/repositorio/legislacao/decreto/1976/decreto-8468-08.09.1976.html",
    },
    {
        "source_id": "alesp-lei-997-1976",
        "urn": "urn:lex:br;sao.paulo:estadual:lei:1976-05-31;997",
        "title": "Lei 997/1976 (SP) — texto consolidado ALESP",
        "url": "https://www.al.sp.gov.br/repositorio/legislacao/lei/1976/lei-997-31.05.1976.html",
    },
    {
        "source_id": "alesp-lei-13577-2009",
        "urn": "urn:lex:br;sao.paulo:estadual:lei:2009-07-08;13577",
        "title": "Lei 13.577/2009 (SP) — texto consolidado ALESP",
        "url": "https://www.al.sp.gov.br/repositorio/legislacao/lei/2009/lei-13577-08.07.2009.html",
    },
]


def strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{2,}", "\n", text)


def fetch_official(url: str) -> str:
    import urllib.request

    sample_dir = RESULT_DIR / "cache" / "exp04"
    sample_dir.mkdir(parents=True, exist_ok=True)
    import hashlib

    key = sample_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html")
    if key.exists():
        return key.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={"User-Agent": "vela-exp04/0.1 (research)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    key.write_text(body, encoding="utf-8")
    return body


def split_blocks(text: str) -> list[str]:
    """按条/段落切块，与摄入管线同粒度（句号+Art./§ 边界启发式）。"""
    blocks = re.split(r"(?=Art(?:igo)?\.?\s*\d+|§\s*\d+|Par[aá]grafo)", text)
    return [b.strip() for b in blocks if len(b.strip()) > 40]


def generate(from_official: bool = False) -> int:
    samples = []
    if from_official:
        for src in OFFICIAL_SOURCES:
            try:
                text = strip_html(fetch_official(src["url"]))
            except Exception as exc:
                print(f"抓取失败 {src['source_id']}: {exc}")
                continue
            markers = REVISION_MARKERS.findall(text)
            blocks = split_blocks(text)
            samples.append({
                "source_id": src["source_id"],
                "urn": src["urn"],
                "title": src["title"],
                "official_url": src["url"],
                "revision_marker_count": len(markers),
                "blocks": [
                    {"block_index": i, "text": b[:600], "verdict": "", "note": ""}
                    for i, b in enumerate(blocks)
                ],
            })
    else:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        for s in corpus.get("sources", []):
            text = s.get("text_pt", "") or ""
            markers = REVISION_MARKERS.findall(text)
            if not markers:
                continue
            blocks = split_blocks(text)
            samples.append({
                "source_id": s.get("id"),
                "urn": s.get("urn"),
                "title": s.get("title_pt"),
                "revision_marker_count": len(markers),
                "blocks": [
                    {"block_index": i, "text": b[:600], "verdict": "", "note": ""}
                    for i, b in enumerate(blocks)
                ],
            })
    samples.sort(key=lambda x: -x["revision_marker_count"])
    samples = samples[:20]
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    WORKSHEET.write_text(
        json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "instruction": "每块与官方原文比对，verdict 填 ok/error/unsure；error 必须写 note 说明错在哪",
            "samples": samples,
        }, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    total_blocks = sum(len(s["blocks"]) for s in samples)
    print(f"含修订注记样本 {len(samples)} 份，共 {total_blocks} 块，工作表已写入 {WORKSHEET}")
    if not samples:
        print("警告：语料中未检出含修订注记的条目——说明现有语料多为片段摘录而非整合全文，这本身是实验发现，应记录。")
    return 0


def score() -> int:
    data = json.loads(WORKSHEET.read_text(encoding="utf-8"))
    verdicts = [b["verdict"] for s in data["samples"] for b in s["blocks"]]
    filled = [v for v in verdicts if v in ("ok", "error", "unsure")]
    if not filled:
        print("工作表尚未回填 verdict，先人工比对。")
        return 1
    if len(filled) < len(verdicts):
        print(f"警告：{len(verdicts) - len(filled)}/{len(verdicts)} 块未回填，以下比率仅基于已回填块。")
    errors = sum(1 for v in filled if v == "error")
    unsure = sum(1 for v in filled if v == "unsure")
    err_rate = errors / len(filled) * 100
    verdict = (
        f"块级误差率 {err_rate:.1f}% ≤ 5% → A 层可承诺'与来源快照逐块一致'"
        if err_rate <= 5
        else f"块级误差率 {err_rate:.1f}% > 5% → A 层承诺降级（见预登记判据），误差率写入技术诚实声明"
    )
    result = {
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "blocks_total": len(verdicts),
        "blocks_filled": len(filled),
        "errors": errors,
        "unsure": unsure,
        "error_rate_pct": round(err_rate, 1),
        "verdict": verdict,
    }
    (RESULT_DIR / "exp04_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "generate"
    if cmd == "generate":
        sys.exit(generate(from_official="--from-official" in sys.argv))
    sys.exit(score())
