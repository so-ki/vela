from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.api.llm_settings as llm_settings_api
import app.services.llm_client as llm_client
import app.services.user_preference_service as preferences
from app.api.llm_settings import LlmTestRequest
from app.models.user import User


QWEN_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _development_settings(**overrides):
    values = {
        "is_production": False,
        "deepseek_api_key": "",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-chat",
        "qwen_api_key": "",
        "qwen_base_url": QWEN_BASE,
        "qwen_model": "qwen-plus",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def _clear_session_secrets():
    for user_id in range(1, 20):
        llm_client.clear_user_api_key(user_id)
    yield
    for user_id in range(1, 20):
        llm_client.clear_user_api_key(user_id)


def test_user_key_never_reaches_json_or_response_and_can_be_cleared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(preferences, "PREFS_DIR", tmp_path)
    secret = "vela-test-secret-never-persist"

    response = preferences.update_user_llm_settings(
        7,
        {
            "enabled": True,
            "provider": "qwen",
            "base_url": QWEN_BASE,
            "api_key": secret,
        },
    )

    disk_text = (tmp_path / "user_7.json").read_text(encoding="utf-8")
    assert secret not in disk_text
    assert "api_key" not in json.loads(disk_text)["llm_settings"]
    assert secret not in json.dumps(response, ensure_ascii=False)
    assert response["api_key_masked"] == "********"
    assert response["has_api_key"] is True

    cleared = preferences.update_user_llm_settings(7, {"clear_api_key": True})
    assert cleared["has_api_key"] is False
    assert llm_client.user_api_key_binding(7) is None


def test_legacy_plaintext_key_is_scrubbed_without_importing_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(preferences, "PREFS_DIR", tmp_path)
    path = tmp_path / "user_8.json"
    path.write_text(
        json.dumps(
            {
                "user_id": 8,
                "llm_settings": {
                    "enabled": True,
                    "provider": "qwen",
                    "base_url": QWEN_BASE,
                    "api_key": "legacy-plaintext-secret",
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = preferences.load_user_preferences(8)
    assert "api_key" not in loaded["llm_settings"]
    assert "legacy-plaintext-secret" not in path.read_text(encoding="utf-8")
    assert llm_client.has_user_api_key(8) is False


def test_blank_key_with_changed_provider_never_calls_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(preferences, "PREFS_DIR", tmp_path)
    preferences.update_user_llm_settings(
        9,
        {
            "enabled": True,
            "provider": "qwen",
            "base_url": QWEN_BASE,
            "api_key": "bound-qwen-secret",
        },
    )
    calls = []
    monkeypatch.setattr(
        llm_settings_api,
        "test_llm_connection",
        lambda **kwargs: calls.append(kwargs),
    )

    result = llm_settings_api.test_llm(
        LlmTestRequest(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            api_key="",
        ),
        current_user=User(id=9),
    )

    assert result["ok"] is False
    assert calls == []
    assert "bound-qwen-secret" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://dashscope.aliyuncs.com/compatible-mode/v1",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/v1",
        "https://user:pass@dashscope.aliyuncs.com/compatible-mode/v1",
        "https://dashscope.aliyuncs.com.evil.example/compatible-mode/v1",
    ],
)
def test_unsafe_or_non_official_url_is_rejected_before_client_creation(
    url: str,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(llm_client, "get_settings", lambda: _development_settings())
    monkeypatch.setattr(
        llm_client.httpx,
        "Client",
        lambda *args, **kwargs: pytest.fail("network client must not be created"),
    )

    with pytest.raises(llm_client.LlmSecurityError):
        llm_client.chat_completion_raw(
            {
                "provider": "qwen",
                "base_url": url,
                "api_key": "must-not-leave",
                "model": "qwen-plus",
            },
            system="system",
            user="uploaded material",
        )


def test_anonymous_call_never_uses_environment_key_or_opens_network(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: _development_settings(qwen_api_key="server-environment-secret"),
    )
    monkeypatch.setattr(
        llm_client.httpx,
        "Client",
        lambda *args, **kwargs: pytest.fail("anonymous calls must have zero outbound traffic"),
    )

    result, error = llm_client.chat_completion_json(
        None,
        "extract",
        "system",
        "sensitive uploaded material",
    )
    assert result is None
    assert error == "未配置 LLM"


def test_environment_key_with_changed_origin_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(preferences, "PREFS_DIR", tmp_path)
    preferences.update_user_llm_settings(
        10,
        {"enabled": True, "provider": "qwen", "base_url": QWEN_BASE},
    )
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: _development_settings(
            qwen_api_key="server-environment-secret",
            qwen_base_url="https://attacker.example/v1",
        ),
    )
    monkeypatch.setattr(
        llm_client.httpx,
        "Client",
        lambda *args, **kwargs: pytest.fail("invalid environment origin must have zero outbound traffic"),
    )

    assert llm_client.get_llm_config(10, task="polish") is None


def test_redirect_is_not_followed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(llm_client, "get_settings", lambda: _development_settings())

    class RedirectResponse:
        is_redirect = True

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, *args, **kwargs):
            return RedirectResponse()

    monkeypatch.setattr(llm_client.httpx, "Client", FakeClient)
    with pytest.raises(llm_client.LlmSecurityError, match="重定向"):
        llm_client.chat_completion_raw(
            {
                "provider": "qwen",
                "base_url": QWEN_BASE,
                "api_key": "redirect-safe-secret",
                "model": "qwen-plus",
            },
            system="system",
            user="material",
        )


def test_production_connection_test_is_zero_outbound(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: SimpleNamespace(is_production=True),
    )
    monkeypatch.setattr(
        llm_client.httpx,
        "Client",
        lambda *args, **kwargs: pytest.fail("production LLM egress must stay disabled"),
    )

    with pytest.raises(llm_client.LlmSecurityError, match="生产环境"):
        llm_client.test_llm_connection(
            provider="qwen",
            base_url=QWEN_BASE,
            api_key="must-not-leave",
            model="qwen-plus",
        )
