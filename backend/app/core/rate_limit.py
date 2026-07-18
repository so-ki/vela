"""Small, bounded ASGI rate limiter for the single-worker pilot boundary."""

from __future__ import annotations

import ipaddress
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Callable

from starlette.responses import JSONResponse


@dataclass(frozen=True)
class RateLimitRule:
    path: str
    methods: frozenset[str]
    requests: int
    window_seconds: int
    max_body_bytes: int | None = None


DEFAULT_RULES = (
    RateLimitRule("/api/v1/auth/login", frozenset({"POST"}), 10, 60),
    RateLimitRule("/api/v1/auth/register", frozenset({"POST"}), 5, 3600),
    RateLimitRule("/api/v1/auth/sso/login", frozenset({"GET"}), 10, 60),
    RateLimitRule("/api/v1/scenarios/extract-document", frozenset({"POST"}), 10, 60),
    RateLimitRule("/api/v1/scenarios/extract-documents", frozenset({"POST"}), 5, 60),
    RateLimitRule("/api/v1/scenarios/submit-materials", frozenset({"POST"}), 10, 3600),
    RateLimitRule(
        "/api/v1/onboarding/interview/start",
        frozenset({"POST"}),
        10,
        3600,
        max_body_bytes=4 * 1024,
    ),
    RateLimitRule(
        "/api/v1/onboarding/interview/{session_id}/answer",
        frozenset({"POST"}),
        120,
        3600,
        max_body_bytes=80 * 1024,
    ),
    RateLimitRule(
        "/api/v1/onboarding/interview/{session_id}/sync",
        frozenset({"POST"}),
        30,
        3600,
        max_body_bytes=80 * 1024,
    ),
    RateLimitRule(
        "/api/v1/onboarding/interview/{session_id}/upload",
        frozenset({"POST"}),
        10,
        3600,
        max_body_bytes=26 * 1024 * 1024,
    ),
    RateLimitRule(
        "/api/v1/onboarding/interview/complete",
        frozenset({"POST"}),
        10,
        3600,
        max_body_bytes=4 * 1024,
    ),
    RateLimitRule(
        "/api/v1/onboarding/templates",
        frozenset({"POST"}),
        10,
        3600,
        max_body_bytes=26 * 1024 * 1024,
    ),
)
MAX_TRACKED_CLIENTS = 10_000


def _client_key(scope: dict) -> str:
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1").strip()
        for key, value in scope.get("headers", [])
    }
    # The production backend is not published directly; its Nginx peer always
    # overwrites X-Real-IP.  Invalid values cannot create attacker-controlled
    # unbounded keys and fall back to the direct peer address.
    candidate = headers.get("x-real-ip", "")
    try:
        if candidate:
            return str(ipaddress.ip_address(candidate))
    except ValueError:
        pass
    client = scope.get("client") or ("unknown", 0)
    return str(client[0])


def _content_length(scope: dict) -> int | None:
    for key, value in scope.get("headers", []):
        if key.decode("latin-1").lower() != "content-length":
            continue
        try:
            parsed = int(value.decode("latin-1").strip())
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


class _RequestBodyTooLarge(Exception):
    pass


def _path_matches(pattern: str, path: str) -> bool:
    """Match exact paths plus single-segment ``{parameter}`` route templates."""

    pattern_parts = pattern.strip("/").split("/")
    path_parts = path.strip("/").split("/")
    if len(pattern_parts) != len(path_parts):
        return False
    return all(
        bool(path_part)
        if pattern_part.startswith("{") and pattern_part.endswith("}")
        else pattern_part == path_part
        for pattern_part, path_part in zip(pattern_parts, path_parts)
    )


class RateLimitMiddleware:
    def __init__(
        self,
        app,
        *,
        rules: tuple[RateLimitRule, ...] = DEFAULT_RULES,
        clock: Callable[[], float] = time.monotonic,
        max_tracked_clients: int = MAX_TRACKED_CLIENTS,
    ) -> None:
        self.app = app
        self.rules = rules
        self.clock = clock
        self.max_tracked_clients = max(1, int(max_tracked_clients))
        self._events: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method") or "").upper()
        path = str(scope.get("path") or "")
        rule = next(
            (
                item
                for item in self.rules
                if method in item.methods and _path_matches(item.path, path)
            ),
            None,
        )
        if rule is None:
            await self.app(scope, receive, send)
            return

        now = self.clock()
        # Use the canonical rule path, not an attacker-controlled dynamic path,
        # so rotating session ids cannot bypass the bucket or create state keys.
        key = (rule.path, _client_key(scope))
        retry_after = 0
        with self._lock:
            events = self._events.setdefault(key, deque())
            self._events.move_to_end(key)
            cutoff = now - rule.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= rule.requests:
                retry_after = max(1, int(rule.window_seconds - (now - events[0])) + 1)
            else:
                events.append(now)
            while len(self._events) > self.max_tracked_clients:
                self._events.popitem(last=False)

        if retry_after:
            response = JSONResponse(
                {"detail": "请求过于频繁，请稍后重试"},
                status_code=429,
                headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return

        max_body_bytes = rule.max_body_bytes
        if max_body_bytes is None:
            await self.app(scope, receive, send)
            return

        declared_length = _content_length(scope)
        if declared_length is not None and declared_length > max_body_bytes:
            response = JSONResponse(
                {"detail": "请求体超过该接口允许的大小"},
                status_code=413,
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return

        received_bytes = 0
        response_started = False

        async def bounded_receive():
            nonlocal received_bytes
            message = await receive()
            if message.get("type") == "http.request":
                received_bytes += len(message.get("body") or b"")
                if received_bytes > max_body_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, tracked_send)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            response = JSONResponse(
                {"detail": "请求体超过该接口允许的大小"},
                status_code=413,
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
