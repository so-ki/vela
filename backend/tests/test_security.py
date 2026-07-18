from __future__ import annotations

from datetime import timedelta

import jwt

from app.core import security


def test_access_token_round_trip() -> None:
    token = security.create_access_token("person@example.com")

    assert security.decode_access_token(token) == "person@example.com"


def test_expired_access_token_is_rejected() -> None:
    token = security.create_access_token(
        "person@example.com",
        expires_delta=timedelta(seconds=-1),
    )

    assert security.decode_access_token(token) is None


def test_access_token_requires_string_subject() -> None:
    token = jwt.encode(
        {"sub": 123},
        security.settings.secret_key,
        algorithm=security.settings.algorithm,
    )

    assert security.decode_access_token(token) is None


def test_invalid_signature_is_rejected() -> None:
    token = jwt.encode(
        {"sub": "person@example.com"},
        "a-different-signing-secret-that-is-at-least-32-bytes",
        algorithm=security.settings.algorithm,
    )

    assert security.decode_access_token(token) is None
