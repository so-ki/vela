"""Fail-closed LLM client with short-lived, origin-bound user credentials.

User API keys are intentionally never persisted.  They live only in this
process for a short period and are bound to one audited provider endpoint.
Every outbound call validates the binding again immediately before sending.
"""

from __future__ import annotations

import ipaddress
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Literal, Optional, Tuple
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings

TaskName = Literal["polish", "extract", "issue_id", "gap", "red_team"]


class LlmSecurityError(ValueError):
    """A fail-closed LLM egress policy violation safe to show to the user."""


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
}

USER_SECRET_TTL_SECONDS = 60 * 60
MAX_API_KEY_LENGTH = 8192


@dataclass(frozen=True)
class _UserSecret:
    api_key: str
    provider: str
    base_url: str
    expires_at: float


_USER_SECRETS: dict[int, _UserSecret] = {}
_USER_SECRETS_LOCK = threading.RLock()


def _mask_key(key: str) -> str:
    """Never reveal even the prefix/suffix of a credential in API responses."""
    return "********" if key else ""


def _normalised_host(hostname: str) -> str:
    try:
        return hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise LlmSecurityError("LLM Base URL 主机名无效") from exc


def _reject_unsafe_host(hostname: str) -> None:
    """Reject literal non-public addresses before provider allow-list checks."""
    try:
        address = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
        or address.is_multicast
    ):
        raise LlmSecurityError("LLM Base URL 不得指向本机或非公网地址")


def validate_provider_base_url(provider: str, base_url: str = "") -> str:
    """Return the one canonical HTTPS base URL approved for ``provider``.

    Custom OpenAI-compatible endpoints are intentionally outside the audited
    release boundary.  Exact provider and base-path matching also prevents a
    credential saved for one provider from being replayed to another host.
    """
    provider_id = (provider or "").strip().lower()
    defaults = PROVIDER_DEFAULTS.get(provider_id)
    if defaults is None:
        raise LlmSecurityError("该 LLM Provider 不在受控发布白名单内")

    supplied = (base_url or defaults["base_url"]).strip()
    parsed = urlsplit(supplied)
    if parsed.scheme.lower() != "https":
        raise LlmSecurityError("LLM Base URL 必须使用 HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise LlmSecurityError("LLM Base URL 不得包含用户信息")
    if not parsed.hostname:
        raise LlmSecurityError("LLM Base URL 缺少有效主机名")
    if parsed.query or parsed.fragment:
        raise LlmSecurityError("LLM Base URL 不得包含查询参数或片段")

    host = _normalised_host(parsed.hostname)
    _reject_unsafe_host(host)
    try:
        port = parsed.port
    except ValueError as exc:
        raise LlmSecurityError("LLM Base URL 端口无效") from exc
    if port not in (None, 443):
        raise LlmSecurityError("LLM Base URL 仅允许标准 HTTPS 端口")

    path = parsed.path.rstrip("/")
    normalised = f"https://{host}{path}"
    canonical = defaults["base_url"].rstrip("/")
    if normalised != canonical:
        raise LlmSecurityError("LLM Base URL 与所选 Provider 的官方端点不匹配")
    return canonical


def store_user_api_key(user_id: int, *, provider: str, base_url: str, api_key: str) -> None:
    """Keep a key in process memory only, bound to its canonical endpoint."""
    if get_settings().is_production:
        raise LlmSecurityError("生产受控试点不接收或保存第三方 LLM 凭据")
    if not user_id:
        raise LlmSecurityError("缺少用户身份，不能保存 LLM 凭据")
    key = (api_key or "").strip()
    if not key:
        raise LlmSecurityError("API Key 不能为空")
    if len(key) > MAX_API_KEY_LENGTH or "\r" in key or "\n" in key:
        raise LlmSecurityError("API Key 格式无效")
    provider_id = (provider or "").strip().lower()
    canonical_base = validate_provider_base_url(provider_id, base_url)
    secret = _UserSecret(
        api_key=key,
        provider=provider_id,
        base_url=canonical_base,
        expires_at=time.monotonic() + USER_SECRET_TTL_SECONDS,
    )
    with _USER_SECRETS_LOCK:
        _USER_SECRETS[int(user_id)] = secret


def clear_user_api_key(user_id: int) -> None:
    with _USER_SECRETS_LOCK:
        _USER_SECRETS.pop(int(user_id), None)


def _get_user_secret(user_id: Optional[int]) -> Optional[_UserSecret]:
    if not user_id:
        return None
    with _USER_SECRETS_LOCK:
        secret = _USER_SECRETS.get(int(user_id))
        if secret and secret.expires_at <= time.monotonic():
            _USER_SECRETS.pop(int(user_id), None)
            return None
        return secret


def has_user_api_key(user_id: int) -> bool:
    return _get_user_secret(user_id) is not None


def user_api_key_binding(user_id: int) -> Optional[tuple[str, str]]:
    """Return non-secret binding metadata for safe settings reconciliation."""
    secret = _get_user_secret(user_id)
    if not secret:
        return None
    return secret.provider, secret.base_url


def get_bound_user_api_key(user_id: int, *, provider: str, base_url: str) -> Optional[str]:
    """Resolve a saved session key only when this request repeats its binding."""
    secret = _get_user_secret(user_id)
    if not secret:
        return None
    provider_id = (provider or "").strip().lower()
    canonical_base = validate_provider_base_url(provider_id, base_url)
    if (provider_id, canonical_base) != (secret.provider, secret.base_url):
        raise LlmSecurityError("空 Key 测试只能使用原 Provider 与官方端点")
    return secret.api_key


def _env_llm_config(provider: str) -> Optional[dict[str, str]]:
    settings = get_settings()
    if settings.is_production:
        return None
    if provider == "deepseek" and settings.deepseek_api_key:
        return {
            "provider": "deepseek",
            "api_key": settings.deepseek_api_key,
            "base_url": validate_provider_base_url("deepseek", settings.deepseek_base_url),
            "model": settings.deepseek_model,
            "source": "env",
        }
    if provider == "qwen" and settings.qwen_api_key:
        return {
            "provider": "qwen",
            "api_key": settings.qwen_api_key,
            "base_url": validate_provider_base_url("qwen", settings.qwen_base_url),
            "model": settings.qwen_model,
            "source": "env",
        }
    return None


def get_llm_config(
    user_id: Optional[int] = None,
    task: TaskName = "polish",
) -> Optional[dict[str, str]]:
    """Resolve an explicitly enabled, identity-bound configuration.

    ``user_id=None`` always returns ``None``.  Uploaded-material extraction
    never falls back to a service environment key; it requires a short-lived
    user credential and separate per-request consent at the extraction layer.
    """
    from app.services.user_preference_service import get_user_llm_settings

    settings = get_settings()
    if not user_id or settings.is_production:
        return None
    user_cfg = get_user_llm_settings(user_id)
    enabled = user_cfg.get("enabled")
    if enabled is not True:
        return None

    provider = (user_cfg.get("provider") or "").strip().lower()
    base_url = (user_cfg.get("base_url") or "").strip()
    default_model = (user_cfg.get("default_model") or "").strip()
    task_models = user_cfg.get("task_models") or {}
    task_model = (task_models.get(task) or "").strip()

    if not provider:
        return None
    try:
        resolved_base = validate_provider_base_url(provider, base_url)
    except LlmSecurityError:
        return None
    prov_defaults = PROVIDER_DEFAULTS[provider]
    resolved_model = task_model or default_model or prov_defaults["default_model"]

    secret = _get_user_secret(user_id)
    if secret:
        if secret.provider != provider or secret.base_url != resolved_base:
            clear_user_api_key(user_id)
            return None
        return {
            "provider": provider,
            "api_key": secret.api_key,
            "base_url": resolved_base,
            "model": resolved_model,
            "source": "user_session",
        }

    if task == "extract":
        return None

    try:
        env_cfg = _env_llm_config(provider)
    except LlmSecurityError:
        return None
    if not env_cfg:
        return None
    if task_model:
        env_cfg = {**env_cfg, "model": task_model}
    elif default_model:
        env_cfg = {**env_cfg, "model": default_model}
    return env_cfg


def is_llm_enabled(user_id: Optional[int] = None, task: TaskName = "polish") -> bool:
    return get_llm_config(user_id, task=task) is not None


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
    if get_settings().is_production:
        raise LlmSecurityError("生产环境已禁用第三方 LLM 外发")
    provider = (cfg.get("provider") or "").strip().lower()
    base_url = validate_provider_base_url(provider, cfg.get("base_url") or "")
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key:
        raise LlmSecurityError("缺少可用的短期 API Key")
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
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
    with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        resp = client.post(url, headers=headers, json=body)
        if resp.is_redirect:
            raise LlmSecurityError("LLM 官方端点返回重定向，已拒绝继续发送")
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
    except Exception:
        return None, "LLM 请求失败，已安全回退；请检查受控 Provider 配置"


def test_llm_connection(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    if get_settings().is_production:
        raise LlmSecurityError("生产环境已禁用第三方 LLM 外发")
    provider = (provider or "").strip().lower()
    resolved_base = validate_provider_base_url(provider, base_url)
    key = (api_key or "").strip()
    if not key:
        raise LlmSecurityError("请提供短期 API Key")
    resolved_model = model or PROVIDER_DEFAULTS[provider]["default_model"]
    cfg = {
        "provider": provider,
        "api_key": key,
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
    except Exception:
        safe_error = "LLM 请求失败，已安全回退；未改变模板内容"
        brief = {**brief, "mode": "template", "llm_error": safe_error}
        return brief, safe_error


def mask_api_key_for_response(key: str) -> str:
    return _mask_key(key)
