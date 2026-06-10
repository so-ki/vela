"""LLM client with per-user settings and task-specific models."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Literal, Optional, Tuple

import httpx

from app.core.config import get_settings

TaskName = Literal["polish", "extract", "issue_id", "gap", "red_team"]

POLISH_SYSTEM = """你是 Vela 出海法务平台的法律协查写作助手。
任务：在不变更事实与法条依据的前提下，润色中葡双语法律风险简报文本，使其更专业、流畅、适合企业法务阅读。

硬性规则：
1. 不得新增法律结论、法条名称或溯源链接
2. 不得删除「需法务复核」「协查底稿」「不构成正式法律意见」等合规表述
3. 保持每个 item 的 code 不变；blocked 条目原文可不改
4. 仅输出 JSON，不要 markdown 代码块"""

PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "default_model": "deepseek-ai/DeepSeek-V3",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.2",
    },
    "openai_compatible": {
        "base_url": "",
        "default_model": "gpt-4o-mini",
    },
}


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


def _env_llm_config() -> Optional[dict[str, str]]:
    settings = get_settings()
    if settings.deepseek_api_key:
        return {
            "provider": "deepseek",
            "api_key": settings.deepseek_api_key,
            "base_url": settings.deepseek_base_url.rstrip("/"),
            "model": settings.deepseek_model,
            "source": "env",
        }
    if settings.qwen_api_key:
        return {
            "provider": "qwen",
            "api_key": settings.qwen_api_key,
            "base_url": settings.qwen_base_url.rstrip("/"),
            "model": settings.qwen_model,
            "source": "env",
        }
    return None


def get_llm_config(
    user_id: Optional[int] = None,
    task: TaskName = "polish",
) -> Optional[dict[str, str]]:
    """User prefs override env; task_models override default_model."""
    from app.services.user_preference_service import get_user_llm_settings

    settings = get_settings()
    user_cfg = get_user_llm_settings(user_id) if user_id else {}
    enabled = user_cfg.get("enabled")
    if enabled is False:
        return None

    provider = (user_cfg.get("provider") or "").strip()
    api_key = (user_cfg.get("api_key") or "").strip()
    base_url = (user_cfg.get("base_url") or "").strip()
    default_model = (user_cfg.get("default_model") or "").strip()
    task_models = user_cfg.get("task_models") or {}
    task_model = (task_models.get(task) or "").strip()

    if provider and api_key:
        prov_defaults = PROVIDER_DEFAULTS.get(provider, {})
        resolved_base = (base_url or prov_defaults.get("base_url") or "").rstrip("/")
        resolved_model = task_model or default_model or prov_defaults.get("default_model") or "gpt-4o-mini"
        if not resolved_base and provider != "openai_compatible":
            return _env_llm_config()
        return {
            "provider": provider,
            "api_key": api_key,
            "base_url": resolved_base,
            "model": resolved_model,
            "source": "user",
        }

    env_cfg = _env_llm_config()
    if not env_cfg:
        return None
    if task == "polish":
        if enabled is False:
            return None
        if enabled is None and not settings.llm_polish_enabled:
            return None
    elif enabled is False:
        return None
    if task_model:
        env_cfg = {**env_cfg, "model": task_model}
    elif default_model:
        env_cfg = {**env_cfg, "model": default_model}
    return env_cfg


def is_llm_enabled(user_id: Optional[int] = None) -> bool:
    from app.services.user_preference_service import get_user_llm_settings

    user_cfg = get_user_llm_settings(user_id) if user_id else {}
    if user_cfg.get("enabled") is False:
        return False
    if user_cfg.get("enabled") is True and user_cfg.get("api_key"):
        return True
    return get_llm_config(user_id) is not None


def llm_status(user_id: Optional[int] = None) -> dict[str, Any]:
    cfg = get_llm_config(user_id)
    if not cfg:
        return {
            "available": False,
            "provider": None,
            "model": None,
            "message": "未配置 LLM API Key 或已禁用",
        }
    return {
        "available": True,
        "provider": cfg["provider"],
        "model": cfg["model"],
        "message": f"已启用 {cfg['provider']} · {cfg['model']} ({cfg.get('source', 'env')})",
    }


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def chat_completion_raw(
    cfg: dict[str, str],
    *,
    system: str,
    user: str,
    timeout: float = 120.0,
    json_mode: bool = True,
    temperature: float = 0.2,
) -> str:
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


def chat_completion_json(
    user_id: Optional[int],
    task: TaskName,
    system: str,
    user: str,
    *,
    timeout: float = 120.0,
) -> tuple[dict[str, Any] | None, str | None]:
    cfg = get_llm_config(user_id, task=task)
    if not cfg:
        return None, "未配置 LLM"
    try:
        raw = chat_completion_raw(cfg, system=system, user=user, timeout=timeout, json_mode=True)
        return _extract_json(raw), None
    except Exception as exc:
        return None, str(exc)[:200]


def test_llm_connection(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    prov_defaults = PROVIDER_DEFAULTS.get(provider, {})
    resolved_base = (base_url or prov_defaults.get("base_url") or "").rstrip("/")
    resolved_model = model or prov_defaults.get("default_model") or "gpt-4o-mini"
    cfg = {
        "provider": provider,
        "api_key": api_key,
        "base_url": resolved_base,
        "model": resolved_model,
    }
    start = time.perf_counter()
    raw = chat_completion_raw(
        cfg,
        system='Reply JSON only: {"status":"ok"}',
        user='Say {"status":"ok"}',
        timeout=timeout,
        json_mode=True,
        temperature=0.0,
    )
    latency_ms = int((time.perf_counter() - start) * 1000)
    parsed = _extract_json(raw)
    return {
        "ok": parsed.get("status") == "ok",
        "latency_ms": latency_ms,
        "model": resolved_model,
        "provider": provider,
    }


def _chat_completion(cfg: dict[str, str], user_prompt: str, *, timeout: float = 180.0) -> str:
    return chat_completion_raw(
        cfg,
        system=POLISH_SYSTEM,
        user=user_prompt,
        timeout=timeout,
        json_mode=True,
    )


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


def polish_brief(
    brief: dict[str, Any],
    user_id: Optional[int] = None,
) -> Tuple[dict[str, Any], Optional[str]]:
    """Returns (brief, error_message). On failure keeps template text."""
    cfg = get_llm_config(user_id, task="polish")
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


def mask_api_key_for_response(key: str) -> str:
    return _mask_key(key)
