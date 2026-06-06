from __future__ import annotations

import json
import re
from typing import Any, Optional, Tuple

import httpx

from app.core.config import get_settings
from app.services.llm_client import get_llm_config

VALID_DIMENSIONS = {"labor", "foreign_investment", "tax", "industry_access"}

INTENT_SYSTEM = """你是 Vela 出海法务平台的意图解析助手。
任务：从中文巴西投资场景描述中抽取审查维度与关键词，辅助生成《专项核查清单》（不限于设厂）。

硬性规则：
1. 仅输出 JSON，不要 markdown
2. dimensions 只能从以下取值中选择子集：labor, foreign_investment, tax, industry_access
3. 不得编造具体法条或结论
4. summary_zh 一句话概括场景合规关注点（≤80字）"""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def parse_scenario_intent(
    *,
    description: str,
    project_name: str = "",
    investment_structure: str = "",
) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
    """Returns (intent_payload, error). Skips when LLM not configured."""
    cfg = get_llm_config()
    if not cfg or not get_settings().llm_polish_enabled:
        return None, "未配置 LLM，使用规则引擎解析"

    user_text = "\n".join(
        filter(None, [f"项目名称：{project_name}", f"投资结构：{investment_structure}", f"场景描述：{description}"])
    )
    prompt = (
        "请解析以下出海场景，返回 JSON："
        '{"dimensions":["labor",...], "keywords":["..."], "summary_zh":"..."}\n\n'
        f"{user_text}"
    )

    try:
        url = f"{cfg['base_url']}/chat/completions"
        body = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": INTENT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
                json=body,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
        parsed = _extract_json(raw)
        dims = [d for d in parsed.get("dimensions", []) if d in VALID_DIMENSIONS]
        return {
            "mode": "llm",
            "provider": cfg["provider"],
            "dimensions": dims,
            "keywords": parsed.get("keywords", [])[:12],
            "summary_zh": parsed.get("summary_zh", ""),
        }, None
    except Exception as exc:
        return None, str(exc)[:200]
