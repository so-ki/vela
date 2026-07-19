#!/usr/bin/env python3
"""Fail closed when finalist-facing surfaces drift from approved claims."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POSITIONING = (
    "Vela 是面向中国企业法务的拉美投资前合规协查过程保证平台。"
    "本次以圣保罗州新能源绿地设厂为首个能力包，提供六维初步协查，"
    "其中环境许可为重点深度验证模块；不承诺市级完整覆盖、全巴西覆盖或实时完整更新。"
)
SURFACES = (
    Path("README.md"),
    Path("frontend/src/views/CompetitionWorkspaceView.vue"),
    Path("操作手册.md"),
    Path("客户操作手册.md"),
    Path("docs/星瀚杯_3分钟汇报稿_泳道简版.md"),
)
BLOCKED_PATTERNS = {
    "30 checklist items must not be called legal rule cards": re.compile(
        r"30\s*张(?:可运行)?规则卡"
    ),
    "no nationwide completeness claim": re.compile(
        r"巴西全国完整覆盖|完整覆盖巴西全国"
    ),
    "no municipal completeness claim": re.compile(r"市级完整覆盖"),
    "no complete real-time update claim": re.compile(r"实时完整更新"),
    "no affirmative formal legal opinion claim": re.compile(
        r"(?:提供|出具|形成|等同于|作为)正式法律意见|(?<!不)构成正式法律意见"
    ),
    "no completed lawyer certification claim": re.compile(r"律师认证已完成"),
    "no completed customer acceptance claim": re.compile(r"客户验收已完成"),
}


def main() -> int:
    failures: list[str] = []
    for relative in SURFACES:
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"missing finalist surface: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        if POSITIONING not in text:
            failures.append(f"canonical positioning missing: {relative}")
        searchable = text.replace(POSITIONING, "")
        for label, pattern in BLOCKED_PATTERNS.items():
            match = pattern.search(searchable)
            if match:
                failures.append(
                    f"{relative}: {label}: {match.group(0)!r}"
                )
    if failures:
        print("Competition claim scan failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Competition claim scan passed: {len(SURFACES)} surfaces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
