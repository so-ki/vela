"""实验① 州级元数据完备率.

对首包（br-sp-new-energy）30 条目标法规逐条查 LexML，记录：
  1. urn_resolvable   —— SRU 按 URN 精确检索有记录
  2. metadata_present —— SRU 记录含标题/日期等 DC 元数据
  3. changes_available—— LexML 详情页含修订关系线索（legislationChanges / "Alterada por" 等）
  4. text_link_present—— 详情页含全文链接（planalto / al.sp.gov.br / in.gov.br 等）

判据先行（见 docs/experiments/README.md，2026-07-18 预登记）：
  州级（SP）条目 "URN 可解析且元数据存在" 覆盖率 >= 70% -> Citator v1 含州级；否则仅联邦。

用法：
  python scripts/experiment01_state_metadata_coverage.py            # 在线运行并写缓存
  python scripts/experiment01_state_metadata_coverage.py --offline  # 用缓存重放
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = REPO_ROOT / "docs" / "experiments" / "results"
CACHE_DIR = RESULT_DIR / "cache" / "exp01"

SRU_ENDPOINT = "https://www.lexml.gov.br/busca/SRU"
PAGE_ENDPOINT = "https://www.lexml.gov.br/urn/"

# 首包 30 条目标法规。level: federal / conama / state(SP)
TARGETS = [
    # --- 联邦 (12) ---
    {"id": "F01", "level": "federal", "name": "Lei 6.938/1981 (PNMA 国家环境政策)", "urn": "urn:lex:br:federal:lei:1981-08-31;6938"},
    {"id": "F02", "level": "federal", "name": "Lei Complementar 140/2011 (环境许可权限划分)", "urn": "urn:lex:br:federal:lei.complementar:2011-12-08;140"},
    {"id": "F03", "level": "federal", "name": "Lei 9.605/1998 (环境犯罪法)", "urn": "urn:lex:br:federal:lei:1998-02-12;9605"},
    {"id": "F04", "level": "federal", "name": "Lei 12.305/2010 (固废政策)", "urn": "urn:lex:br:federal:lei:2010-08-02;12305"},
    {"id": "F05", "level": "federal", "name": "Lei 12.651/2012 (森林法典)", "urn": "urn:lex:br:federal:lei:2012-05-25;12651"},
    {"id": "F06", "level": "federal", "name": "Lei 9.985/2000 (SNUC 保护区体系)", "urn": "urn:lex:br:federal:lei:2000-07-18;9985"},
    {"id": "F07", "level": "federal", "name": "Decreto-Lei 5.452/1943 (CLT 劳动法)", "urn": "urn:lex:br:federal:decreto.lei:1943-05-01;5452"},
    {"id": "F08", "level": "federal", "name": "Lei 13.874/2019 (经济自由法)", "urn": "urn:lex:br:federal:lei:2019-09-20;13874"},
    {"id": "F09", "level": "federal", "name": "Lei 4.131/1962 (外资法)", "urn": "urn:lex:br:federal:lei:1962-09-03;4131"},
    {"id": "F10", "level": "federal", "name": "Lei 13.709/2018 (LGPD 数据保护)", "urn": "urn:lex:br:federal:lei:2018-08-14;13709"},
    {"id": "F11", "level": "federal", "name": "Lei Complementar 87/1996 (Lei Kandir ICMS)", "urn": "urn:lex:br:federal:lei.complementar:1996-09-13;87"},
    {"id": "F12", "level": "federal", "name": "Lei 14.300/2022 (分布式发电框架)", "urn": "urn:lex:br:federal:lei:2022-01-06;14300"},
    # --- CONAMA (6) ---
    {"id": "C01", "level": "conama", "name": "Resolução CONAMA 237/1997 (许可程序)", "urn": "urn:lex:br:conselho.nacional.meio.ambiente:resolucao:1997-12-19;237"},
    {"id": "C02", "level": "conama", "name": "Resolução CONAMA 1/1986 (EIA/RIMA)", "urn": "urn:lex:br:conselho.nacional.meio.ambiente:resolucao:1986-01-23;1"},
    {"id": "C03", "level": "conama", "name": "Resolução CONAMA 279/2001 (电力简化许可)", "urn": "urn:lex:br:conselho.nacional.meio.ambiente:resolucao:2001-06-27;279"},
    {"id": "C04", "level": "conama", "name": "Resolução CONAMA 302/2002 (水库周边 APP)", "urn": "urn:lex:br:conselho.nacional.meio.ambiente:resolucao:2002-03-20;302"},
    {"id": "C05", "level": "conama", "name": "Resolução CONAMA 357/2005 (水体分类)", "urn": "urn:lex:br:conselho.nacional.meio.ambiente:resolucao:2005-03-17;357"},
    {"id": "C06", "level": "conama", "name": "Resolução CONAMA 462/2014 (风电许可)", "urn": "urn:lex:br:conselho.nacional.meio.ambiente:resolucao:2014-07-24;462"},
    # --- 圣保罗州 (12) ---
    {"id": "S01", "level": "state", "name": "Lei 997/1976 (SP 污染控制)", "urn": "urn:lex:br;sao.paulo:estadual:lei:1976-05-31;997"},
    {"id": "S02", "level": "state", "name": "Decreto 8.468/1976 (SP 997 实施细则)", "urn": "urn:lex:br;sao.paulo:estadual:decreto:1976-09-08;8468"},
    {"id": "S03", "level": "state", "name": "Lei 13.577/2009 (SP 污染场地)", "urn": "urn:lex:br;sao.paulo:estadual:lei:2009-07-08;13577"},
    {"id": "S04", "level": "state", "name": "Decreto 59.263/2013 (SP 13.577 实施细则)", "urn": "urn:lex:br;sao.paulo:estadual:decreto:2013-06-05;59263"},
    {"id": "S05", "level": "state", "name": "Lei 12.300/2006 (SP 固废政策)", "urn": "urn:lex:br;sao.paulo:estadual:lei:2006-03-16;12300"},
    {"id": "S06", "level": "state", "name": "Decreto 47.397/2002 (SP 许可制度修订)", "urn": "urn:lex:br;sao.paulo:estadual:decreto:2002-12-04;47397"},
    {"id": "S07", "level": "state", "name": "Lei 9.509/1997 (SP 州环境政策)", "urn": "urn:lex:br;sao.paulo:estadual:lei:1997-03-20;9509"},
    {"id": "S08", "level": "state", "name": "Lei 7.663/1991 (SP 水资源)", "urn": "urn:lex:br;sao.paulo:estadual:lei:1991-12-30;7663"},
    {"id": "S09", "level": "state", "name": "Lei 13.798/2009 (SP 气候变化政策)", "urn": "urn:lex:br;sao.paulo:estadual:lei:2009-11-09;13798"},
    {"id": "S10", "level": "state", "name": "Decreto 55.947/2010 (SP 气候政策细则)", "urn": "urn:lex:br;sao.paulo:estadual:decreto:2010-06-24;55947"},
    {"id": "S11", "level": "state", "name": "Lei 6.134/1988 (SP 地下水)", "urn": "urn:lex:br;sao.paulo:estadual:lei:1988-06-02;6134"},
    {"id": "S12", "level": "state", "name": "Decreto 32.955/1991 (SP 地下水细则)", "urn": "urn:lex:br;sao.paulo:estadual:decreto:1991-02-07;32955"},
]

CHANGES_MARKERS = [
    "legislationChanges", "Alterada por", "Alterado por", "alterada pela", "alterado pelo",
    "Revogada por", "Revogado por", "Regulamentada por", "Regulamentado por",
    "Vide alterações", "apelidoRelacao",
]
TEXT_LINK_PATTERN = re.compile(
    r"https?://(?:www\.)?(planalto\.gov\.br|al\.sp\.gov\.br|in\.gov\.br|normas\.leg\.br|"
    r"legislacao\.sp\.gov\.br|cetesb\.sp\.gov\.br|conama|senado\.leg\.br)[^\s\"'<>]*",
    re.IGNORECASE,
)


def cache_key(url: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".cache")


def fetch(url: str, offline: bool) -> tuple[str, str]:
    """返回 (body, source)。source ∈ {live, cache, error:<msg>}。在线时写缓存。"""
    key = cache_key(url)
    if offline:
        if key.exists():
            return key.read_text(encoding="utf-8"), "cache"
        return "", "error:no-cache"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "vela-exp01/0.1 (research; contact team)"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key.write_text(body, encoding="utf-8")
        return body, "live"
    except Exception as exc:  # 记录而非中断：不可达本身是实验数据
        return "", f"error:{type(exc).__name__}:{exc}"


def sru_query(urn: str, offline: bool) -> tuple[int, bool, str]:
    """按 URN 精确检索。返回 (记录数, 元数据存在, 来源)。"""
    query = urllib.parse.quote(f'urn="{urn}"')
    url = f"{SRU_ENDPOINT}?operation=searchRetrieve&version=1.1&maximumRecords=1&query={query}"
    body, source = fetch(url, offline)
    if not body:
        return -1, False, source
    m = re.search(r"<srw:numberOfRecords>(\d+)</srw:numberOfRecords>", body)
    n = int(m.group(1)) if m else 0
    has_metadata = n > 0 and ("<srw:recordData>" in body) and ("urn" in body)
    return n, has_metadata, source


def page_probe(urn: str, offline: bool) -> tuple[bool, bool, str]:
    """抓详情页，返回 (修订关系线索, 全文链接存在, 来源)。"""
    url = PAGE_ENDPOINT + urn
    body, source = fetch(url, offline)
    if not body:
        return False, False, source
    changes = any(marker.lower() in body.lower() for marker in CHANGES_MARKERS)
    text_link = bool(TEXT_LINK_PATTERN.search(body))
    return changes, text_link, source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="用缓存重放，不发网络请求")
    args = parser.parse_args()

    rows = []
    for t in TARGETS:
        n, meta, src1 = sru_query(t["urn"], args.offline)
        changes, text_link, src2 = (False, False, "skipped")
        if n > 0:
            changes, text_link, src2 = page_probe(t["urn"], args.offline)
        rows.append({
            **t,
            "sru_records": n,
            "urn_resolvable": n > 0,
            "metadata_present": meta,
            "changes_available": changes,
            "text_link_present": text_link,
            "fetch_source": f"sru={src1};page={src2}",
        })
        print(f"{t['id']} {t['level']:<7} records={n:>2} meta={meta} changes={changes} text={text_link}  {t['name']}")
        if not args.offline:
            time.sleep(1.0)

    def rate(items, key):
        items = list(items)
        return (sum(1 for r in items if r[key]) / len(items) * 100) if items else 0.0

    by_level = {}
    for level in ("federal", "conama", "state"):
        subset = [r for r in rows if r["level"] == level]
        by_level[level] = {
            "n": len(subset),
            "urn_resolvable_pct": round(rate(subset, "urn_resolvable"), 1),
            "resolvable_and_metadata_pct": round(
                sum(1 for r in subset if r["urn_resolvable"] and r["metadata_present"]) / len(subset) * 100, 1
            ) if subset else 0.0,
            "changes_available_pct": round(rate(subset, "changes_available"), 1),
            "text_link_pct": round(rate(subset, "text_link_present"), 1),
        }

    state_cov = by_level["state"]["resolvable_and_metadata_pct"]
    verdict = (
        f"州级覆盖率 {state_cov}% ≥ 70% → 按预登记判据：Citator v1 含州级"
        if state_cov >= 70
        else f"州级覆盖率 {state_cov}% < 70% → 按预登记判据：Citator v1 仅承诺联邦级，州级标注'人工核对'"
    )

    ts = datetime.now(timezone.utc).isoformat()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULT_DIR / "exp01_raw.json"
    raw_path.write_text(
        json.dumps({"run_at": ts, "offline": args.offline, "rows": rows, "by_level": by_level, "verdict": verdict},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    md = ["# 实验① 结果：州级元数据完备率", "", f"- 运行时间：{ts}", f"- 模式：{'离线重放' if args.offline else '在线'}",
          f"- 原始数据：`exp01_raw.json`；响应缓存：`cache/exp01/`", "",
          "## 分层覆盖率", "", "| 层级 | n | URN可解析 | 可解析+元数据 | 修订关系可得 | 全文链接 |", "|---|---|---|---|---|---|"]
    for level, s in by_level.items():
        md.append(f"| {level} | {s['n']} | {s['urn_resolvable_pct']}% | {s['resolvable_and_metadata_pct']}% | "
                  f"{s['changes_available_pct']}% | {s['text_link_pct']}% |")
    md += ["", f"## 判据裁决（判据 2026-07-18 预登记于 README.md，先于运行）", "", f"**{verdict}**", "",
           "## 逐条明细", "", "| ID | 层级 | 法规 | 记录数 | 元数据 | 修订关系 | 全文链接 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['id']} | {r['level']} | {r['name']} | {r['sru_records']} | "
                  f"{'✓' if r['metadata_present'] else '✗'} | {'✓' if r['changes_available'] else '✗'} | "
                  f"{'✓' if r['text_link_present'] else '✗'} |")
    (RESULT_DIR / "exp01_result.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n" + verdict)
    print(f"结果已写入 {RESULT_DIR / 'exp01_result.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
