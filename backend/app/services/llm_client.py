from __future__ import annotations

import json
import re
from typing import Any, Optional, Tuple

import httpx

from app.core.config import get_settings

POLISH_SYSTEM = """你是 Vela 出海法务平台的法律协查写作助手。
任务：在不变更事实与法条依据的前提下，润色中葡双语法律风险简报文本，使其更专业、流畅、适合企业法务阅读。

硬性规则：
1. 不得新增法律结论、法条名称或溯源链接
2. 不得删除「需法务复核」「协查底稿」「不构成正式法律意见」等合规表述
3. 保持每个 item 的 code 不变；blocked 条目原文可不改
4. 仅输出 JSON，不要 markdown 代码块"""


def get_llm_config() -> Optional[dict[str, str]]:
    settings = get_settings()
    if settings.deepseek_api_key:
        return {
            "provider": "deepseek",
            "api_key": settings.deepseek_api_key,
            "base_url": settings.deepseek_base_url.rstrip("/"),
            "model": settings.deepseek_model,
        }
    if settings.qwen_api_key:
        return {
            "provider": "qwen",
            "api_key": settings.qwen_api_key,
            "base_url": settings.qwen_base_url.rstrip("/"),
            "model": settings.qwen_model,
        }
    return None


def llm_status() -> dict[str, Any]:
    cfg = get_llm_config()
    if not cfg:
        return {"available": False, "provider": None, "model": None, "message": "未配置 DEEPSEEK_API_KEY 或 QWEN_API_KEY"}
    return {
        "available": True,
        "provider": cfg["provider"],
        "model": cfg["model"],
        "message": f"已启用 {cfg['provider']} · {cfg['model']}",
    }


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _chat_completion(cfg: dict[str, str], user_prompt: str, *, timeout: float = 180.0) -> str:
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    body = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": POLISH_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


def _build_polish_prompt(brief: dict[str, Any]) -> str:
    payload = {
        "summary_zh": brief["summary_zh"],
        "summary_pt": brief["summary_pt"],
        "sections": [
            {
                "dimension_id": section["dimension_id"],
                "summary_zh": section["summary_zh"],
                "summary_pt": section["summary_pt"],
                "items": [
                    {
                        "code": item["code"],
                        "risk_zh": item["risk_zh"],
                        "risk_pt": item["risk_pt"],
                    }
                    for item in section["items"]
                    if item.get("gate_status") == "passed"
                ],
            }
            for section in brief["sections"]
        ],
    }
    return (
        "请润色以下 JSON 中的 summary_zh、summary_pt、sections[].summary_zh/pt "
        "以及 sections[].items[].risk_zh/risk_pt。"
        "返回相同 JSON 结构，仅改进措辞：\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _merge_polish(brief: dict[str, Any], polished: dict[str, Any]) -> dict[str, Any]:
    out = {**brief}
    out["summary_zh"] = polished.get("summary_zh", brief["summary_zh"])
    out["summary_pt"] = polished.get("summary_pt", brief["summary_pt"])

    section_map = {s["dimension_id"]: s for s in polished.get("sections", [])}
    new_sections = []
    for section in brief["sections"]:
        sec = {**section}
        ps = section_map.get(section["dimension_id"], {})
        sec["summary_zh"] = ps.get("summary_zh", section["summary_zh"])
        sec["summary_pt"] = ps.get("summary_pt", section["summary_pt"])

        item_map = {i["code"]: i for i in ps.get("items", [])}
        merged_items = []
        for item in section["items"]:
            mi = {**item}
            if item.get("gate_status") == "passed" and item["code"] in item_map:
                pi = item_map[item["code"]]
                mi["risk_zh"] = pi.get("risk_zh", item["risk_zh"])
                mi["risk_pt"] = pi.get("risk_pt", item["risk_pt"])
            merged_items.append(mi)
        sec["items"] = merged_items
        new_sections.append(sec)

    out["sections"] = new_sections
    return out


def polish_brief(brief: dict[str, Any]) -> Tuple[dict[str, Any], Optional[str]]:
    """Returns (brief, error_message). On failure keeps template text."""
    cfg = get_llm_config()
    if not cfg:
        return brief, "未配置 LLM API Key"

    try:
        raw = _chat_completion(cfg, _build_polish_prompt(brief))
        polished = _extract_json(raw)
        result = _merge_polish(brief, polished)
        result["mode"] = "llm"
        result["llm_provider"] = cfg["provider"]
        result["llm_model"] = cfg["model"]
        return result, None
    except Exception as exc:
        brief = {**brief, "mode": "template", "llm_error": str(exc)[:200]}
        return brief, str(exc)[:200]
