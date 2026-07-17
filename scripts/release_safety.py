#!/usr/bin/env python3
"""Fail-closed Docker and submission-package boundary checks.

The checker reports only file paths and detector names. It never prints matched
secret material. The package builder uses an allowlist and scans the finished
archive before declaring success.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import os
import re
import shlex
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]

DOCKER_TARGETS = (
    ("docker/Dockerfile.backend", "backend"),
    ("docker/Dockerfile.backend.prod", "backend"),
    ("docker/Dockerfile.frontend", "frontend"),
    ("docker/Dockerfile.frontend.prod", "."),
    ("docker/Dockerfile.postgres.prod", "."),
)

FORBIDDEN_PREFIXES = (
    ".git/",
    "data/",
    "backend/.venv/",
    "backend/data/",
    "backend/tests/",
    "backend/app/capability_packs/fixtures/",
    "frontend/node_modules/",
    "frontend/dist/",
    "frontend/src/test/",
)
FORBIDDEN_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    ".vite",
    "__pycache__",
    "backup",
    "backups",
    "chroma",
    "dist",
    "interview_sessions",
    "node_modules",
    "playbook_deviations",
    "playbook_profiles",
    "playbook_templates",
    "scenario_materials",
    "uploads",
    "user_preferences",
    "venv",
}
FORBIDDEN_SUFFIXES = {
    ".db",
    ".bak",
    ".backup",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".pyc",
    ".sqlite",
    ".sqlite3",
    ".tsbuildinfo",
}
FORBIDDEN_RELEASE_FILES = {
    "backend/app/data/corpus_pending_review.json",
    "docs/vela_differentiation.png",
    "docs/vela_differentiation@2x.png",
    "docs/vela_investigation_workflow_v2.xmind",
    "docs/vela_investigation_workflow_v2.opml",
    "docs/vela_system_flow_swimlane.png",
    "docs/vela_system_flow_swimlane@2x.png",
    "scripts/generate_golden_path_fishbone.py",
}
FORBIDDEN_RELEASE_PREFIXES = {
    "docs/vela_investigation_workflow_v2.xmind/",
}
FORBIDDEN_ALWAYS_FILES = {
    "backend/app/data/corpus_pending_review.json",
}
# This browser test is part of the production release verification path rather
# than a development test suite.  It is intentionally shipped so prod_smoke.sh
# remains runnable after extracting the release ZIP.
ALLOWED_RELEASE_TEST_FILES = {
    "frontend/e2e/production-smoke.spec.ts",
}
SECRET_PATTERNS = (
    (
        "private-key",
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    ),
    ("aws-access-key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("provider-api-key", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
)
SENSITIVE_EQUALS_ASSIGNMENT = re.compile(
    rb"(?im)^\s*(?:"
    rb"QWEN_API_KEY|OPENAI_API_KEY|DEEPSEEK_API_KEY|"
    rb"SECRET_KEY|POSTGRES_PASSWORD|DB_PASSWORD|DATABASE_PASSWORD|DATABASE_URL|"
    rb"SSO_CLIENT_SECRET|AWS_SECRET_ACCESS_KEY"
    rb")\s*=\s*([^\r\n#]*)"
)
SENSITIVE_STRUCTURED_ASSIGNMENT = re.compile(
    rb"(?im)^\s*[\"']?(?:"
    rb"QWEN_API_KEY|OPENAI_API_KEY|DEEPSEEK_API_KEY|"
    rb"SECRET_KEY|POSTGRES_PASSWORD|DB_PASSWORD|DATABASE_PASSWORD|DATABASE_URL|"
    rb"SSO_CLIENT_SECRET|AWS_SECRET_ACCESS_KEY"
    rb")[\"']?\s*:(?!\s*[A-Za-z_][A-Za-z0-9_.]*\s*=)\s*([^\r\n#]*)"
)
SENSITIVE_JSON_ASSIGNMENT = re.compile(
    rb"(?i)(?:^|[,{])\s*[\"'](?:"
    rb"QWEN_API_KEY|OPENAI_API_KEY|DEEPSEEK_API_KEY|"
    rb"SECRET_KEY|POSTGRES_PASSWORD|DB_PASSWORD|DATABASE_PASSWORD|DATABASE_URL|"
    rb"SSO_CLIENT_SECRET|AWS_SECRET_ACCESS_KEY"
    rb")[\"']\s*:\s*([^,}\r\n]*)"
)

MAX_ARCHIVE_DEPTH = 3
MAX_ARCHIVE_ENTRIES = 4000
MAX_ARCHIVE_ENTRY_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 128 * 1024 * 1024

ROOT_FILES = (
    ".dockerignore",
    ".gitignore",
    "API.md",
    "DEPLOYMENT.md",
    "GITHUB_SETUP.md",
    "README.md",
    "TESTING.md",
    "docker-compose.prod.yml",
    "docker-compose.yml",
    "客户操作手册.md",
    "操作手册.md",
)

EXPLICIT_RUNTIME_FILES = (
    # The packaged release-boundary checker reads the pinned CI workflow to
    # verify the real Docker/PostgreSQL smoke job.  Keep that evidence with the
    # release so an independent recipient can rerun check-docker after unzip.
    ".github/workflows/ci.yml",
    "backend/.dockerignore",
    "backend/alembic.ini",
    "backend/requirements.lock",
    "backend/requirements-rag.txt",
    "backend/requirements.txt",
    "backend/app/__init__.py",
    "backend/app/main.py",
    "backend/app/capability_packs/__init__.py",
    "backend/app/capability_packs/loader.py",
    "backend/app/capability_packs/registry.py",
    "backend/app/capability_packs/schemas.py",
    "backend/app/data/brazil_legal_corpus.json",
    "backend/app/data/brazil_official_portals.json",
    "backend/app/data/cold_start_interview.json",
    "backend/app/data/contract_house_rules.json",
    "backend/app/data/material_house_rules.json",
    "backend/app/rules/brazil_new_energy.json",
    "backend/app/rules/index.json",
    "backend/scripts/migrate_sqlite.py",
    "backend/scripts/propose_corpus_entry.py",
    "backend/scripts/__init__.py",
    "backend/scripts/container_entrypoint.py",
    "backend/scripts/create_user.py",
    "backend/scripts/render_official_pages_to_pdf.mjs",
    "backend/scripts/run_ingestion_qa.py",
    "backend/scripts/run_legal_quality_gate.py",
    "backend/scripts/run_state_metadata_coverage.py",
    "backend/scripts/seed_demo_user.py",
    "frontend/.dockerignore",
    "frontend/index.html",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/playwright.config.ts",
    "frontend/e2e/production-smoke.spec.ts",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "docker/Dockerfile.backend",
    "docker/Dockerfile.backend.prod",
    "docker/Dockerfile.frontend",
    "docker/Dockerfile.frontend.prod",
    "docker/Dockerfile.postgres.prod",
    "docker/nginx.conf",
)

PACKAGE_TREES = (
    "backend/alembic",
    "backend/app/api",
    "backend/app/core",
    "backend/app/models",
    "backend/app/schemas",
    "backend/app/services",
    "backend/app/capability_packs/brazil_new_energy_greenfield",
    "backend/evals",
    "docs",
    "frontend/public",
    "frontend/src",
)

PACKAGE_SCRIPTS = (
    "scripts/build_submission_package.sh",
    "scripts/check_release_boundaries.sh",
    "scripts/fixtures/sample_storage_project.txt",
    "scripts/init_db.py",
    "scripts/prod_smoke.sh",
    "scripts/purge_demo_scenarios.py",
    "scripts/release_safety.py",
    "scripts/start.sh",
    "scripts/verify_e2e.sh",
    "scripts/verify_incremental.sh",
    "scripts/verify_sso_config.sh",
)

PACKAGE_SUFFIXES = {
    "",
    ".conf",
    ".css",
    ".html",
    ".json",
    ".jsonl",
    ".mako",
    ".md",
    ".mjs",
    ".opml",
    ".png",
    ".py",
    ".sh",
    ".svg",
    ".ts",
    ".vue",
    ".xmind",
}

MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


class BoundaryError(RuntimeError):
    pass


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise BoundaryError(f"路径越出仓库：{path}") from exc


def _path_violations(relative: str, *, release: bool) -> list[str]:
    raw = relative
    normalized = PurePosixPath(relative).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = PurePosixPath(normalized).parts
    lower_normalized = normalized.lower()
    lower_parts = tuple(part.lower() for part in parts)
    violations: list[str] = []
    if (
        not raw
        or raw == "."
        or normalized in {"", "."}
        or raw.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:", raw)
        or ":" in raw
        or ".." in raw.replace("\\", "/").split("/")
        or "\\" in raw
        or any(ord(char) < 32 or ord(char) == 127 for char in raw)
        or any(part in {"", "."} for part in raw.rstrip("/").split("/"))
    ):
        violations.append("unsafe-path")
    if any(
        lower_normalized == prefix.rstrip("/").lower()
        or lower_normalized.startswith(prefix.lower())
        for prefix in FORBIDDEN_PREFIXES
    ):
        violations.append("forbidden-prefix")
    if any(part in FORBIDDEN_PARTS or part.startswith("backup") for part in lower_parts):
        violations.append("forbidden-component")
    filename = lower_parts[-1] if lower_parts else ""
    if (
        PurePosixPath(lower_normalized).suffix in FORBIDDEN_SUFFIXES
        or re.search(r"\.(?:db|sqlite|sqlite3)(?:[-.].*)?$", filename)
    ):
        violations.append("forbidden-suffix")
    if lower_normalized in {path.lower() for path in FORBIDDEN_ALWAYS_FILES}:
        violations.append("forbidden-runtime-source")
    if any(part == ".env" or part.startswith(".env.") or part.endswith(".env") for part in lower_parts):
        violations.append("environment-file")
    if filename == "credentials.json" or ("credential" in filename and filename.endswith(".json")):
        violations.append("credential-file")
    if release and lower_normalized in {path.lower() for path in FORBIDDEN_RELEASE_FILES}:
        violations.append("protected-release-exclusion")
    if release and any(
        lower_normalized.startswith(prefix.lower()) for prefix in FORBIDDEN_RELEASE_PREFIXES
    ):
        violations.append("protected-release-exclusion")
    if (
        release
        and (lower_normalized.endswith(".spec.ts") or lower_normalized.endswith(".test.ts"))
        and lower_normalized not in {path.lower() for path in ALLOWED_RELEASE_TEST_FILES}
    ):
        violations.append("test-source")
    return violations


def _secret_detectors(content: bytes) -> list[str]:
    detectors = [name for name, pattern in SECRET_PATTERNS if pattern.search(content)]
    matches = list(SENSITIVE_EQUALS_ASSIGNMENT.finditer(content))
    matches.extend(SENSITIVE_STRUCTURED_ASSIGNMENT.finditer(content))
    matches.extend(SENSITIVE_JSON_ASSIGNMENT.finditer(content))
    for match in matches:
        value = match.group(1).strip().rstrip(b",").strip().strip(b"\"'")
        lowered = value.lower()
        is_placeholder = (
            not value
            or lowered in {b"null", b"none", b"sk-..."}
            or value.startswith((b"$", b"<"))
            or b"${" in value
            or lowered.startswith(b"sqlite:")
            or any(
                marker in lowered
                for marker in (
                    b"replace",
                    b"example",
                    b"your-",
                    b"change-me",
                    b"changeme",
                    b"redacted",
                    b"placeholder",
                    b"dev-secret",
                    b"_required(",
                    b"os.environ",
                    b"getenv(",
                    b"secrets.",
                )
            )
        )
        if not is_placeholder:
            detectors.append("sensitive-assignment")
            break
    return sorted(set(detectors))


def _read_copy_sources(dockerfile: Path) -> list[str]:
    sources: list[str] = []
    logical_lines: list[str] = []
    pending = ""
    for raw in dockerfile.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pending = f"{pending} {stripped}".strip()
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        logical_lines.append(pending)
        pending = ""
    if pending:
        logical_lines.append(pending)

    for line in logical_lines:
        if not line.upper().startswith("COPY "):
            continue
        tokens = shlex.split(line)
        if any(token.startswith("--from=") for token in tokens[1:]):
            continue
        positional = [token for token in tokens[1:] if not token.startswith("--")]
        if len(positional) < 2:
            raise BoundaryError(f"无法解析 COPY：{_repo_relative(dockerfile)}")
        sources.extend(positional[:-1])
    return sources


def _expand_copy_source(
    context: Path,
    source: str,
    transmitted: set[str] | None = None,
) -> list[Path]:
    if source in {".", "./"}:
        raise BoundaryError("禁止使用全 context COPY")
    if source.startswith(("/", "http://", "https://")) or ".." in PurePosixPath(source).parts:
        raise BoundaryError(f"COPY source 不安全：{source}")
    matches = sorted(context.glob(source)) if any(char in source for char in "*?[") else [context / source]
    if not matches or any(not match.exists() for match in matches):
        raise BoundaryError(f"COPY source 不存在：{source}")
    files: list[Path] = []
    for match in matches:
        match_relative = match.relative_to(context).as_posix()
        if transmitted is not None and match.is_file() and match_relative not in transmitted:
            continue
        if match.is_symlink():
            raise BoundaryError(f"COPY source 不得为符号链接：{_repo_relative(match)}")
        if match.is_dir():
            for path in sorted(match.rglob("*")):
                path_relative = path.relative_to(context).as_posix()
                if transmitted is not None and path_relative not in transmitted:
                    continue
                if path.is_symlink():
                    raise BoundaryError(f"COPY tree 不得含符号链接：{_repo_relative(path)}")
                if path.is_file():
                    files.append(path)
        elif match.is_file():
            files.append(match)
    return files


REQUIRED_DOCKER_DEFENSES = {
    "**/.git/",
    "**/.env",
    "**/.env.*",
    "**/*.env",
    "**/.pytest_cache/",
    "**/.mypy_cache/",
    "**/.vite/",
    "**/.cache/",
    "**/__pycache__/",
    "**/*.tsbuildinfo",
    "**/node_modules/",
    "**/dist/",
    "**/.venv/",
    "**/venv/",
    "**/chroma/",
    "**/user_preferences/",
    "**/playbook_profiles/",
    "**/playbook_templates/",
    "**/playbook_deviations/",
    "**/interview_sessions/",
    "**/uploads/",
    "**/scenario_materials/",
    "**/backup/",
    "**/backups/",
    "**/tmp/",
    "**/temp/",
    "**/*.bak",
    "**/*.backup",
    "**/*.tmp",
    "**/*.db*",
    "**/*.sqlite*",
    "**/*.log",
    "**/*credentials*.json",
}


def _docker_pattern_variants(pattern: str) -> set[str]:
    variants = {pattern}
    pending = [pattern]
    while pending:
        current = pending.pop()
        marker = current.find("**/")
        if marker < 0:
            continue
        reduced = current[:marker] + current[marker + 3 :]
        if reduced not in variants:
            variants.add(reduced)
            pending.append(reduced)
    return variants


def _docker_glob_match(pattern: str, relative: str, *, directory_rule: bool) -> bool:
    anchored = pattern.startswith("/")
    pattern = pattern.lstrip("/")
    if directory_rule:
        pattern = pattern.rstrip("/")
        path_parts = relative.split("/")
        candidates = ["/".join(path_parts[:index]) for index in range(1, len(path_parts) + 1)]
    else:
        candidates = [relative]
    variants = _docker_pattern_variants(pattern)
    if "/" not in pattern and not anchored:
        components = relative.split("/")[:-1] if directory_rule else relative.split("/")
        return any(fnmatch.fnmatchcase(component, pattern) for component in components)
    return any(
        fnmatch.fnmatchcase(candidate, variant)
        for candidate in candidates
        for variant in variants
    )


def _read_dockerignore(ignore: Path) -> list[tuple[bool, str, bool]]:
    rules: list[tuple[bool, str, bool]] = []
    for raw in ignore.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        negated = stripped.startswith("!")
        pattern = stripped[1:] if negated else stripped
        directory_rule = pattern.endswith("/")
        rules.append((negated, pattern, directory_rule))
    return rules


def _is_transmitted(relative: str, rules: list[tuple[bool, str, bool]]) -> bool:
    excluded = False
    for negated, pattern, directory_rule in rules:
        if _docker_glob_match(pattern, relative, directory_rule=directory_rule):
            excluded = not negated
    return not excluded


def _context_transmitted_files(
    context: Path,
    context_rel: str,
    ignore: Path,
    errors: list[str],
) -> dict[str, Path]:
    rules = _read_dockerignore(ignore)
    effective_patterns = [pattern for _, pattern, _ in rules]
    if not rules or rules[0] != (False, "**", False):
        errors.append(f"Docker ignore 首条有效规则必须为 default-deny **：{_repo_relative(ignore)}")
    missing_defenses = sorted(REQUIRED_DOCKER_DEFENSES - set(effective_patterns))
    for pattern in missing_defenses:
        errors.append(f"Docker ignore 缺少防御规则 {pattern}：{_repo_relative(ignore)}")

    transmitted: dict[str, Path] = {}
    for directory, dirnames, filenames in os.walk(context, followlinks=False):
        directory_path = Path(directory)
        for dirname in list(dirnames):
            candidate = directory_path / dirname
            if candidate.is_symlink():
                relative = candidate.relative_to(context).as_posix()
                if _is_transmitted(relative, rules):
                    errors.append(f"Docker context 包含符号链接：{context_rel}:{relative}")
                dirnames.remove(dirname)
        for filename in filenames:
            path = directory_path / filename
            relative = path.relative_to(context).as_posix()
            if not _is_transmitted(relative, rules):
                continue
            repo_relative = relative if context_rel == "." else f"{context_rel}/{relative}"
            if path.is_symlink():
                errors.append(f"Docker context 包含符号链接：{repo_relative}")
                continue
            if not path.is_file():
                errors.append(f"Docker context 包含非普通文件：{repo_relative}")
                continue
            transmitted[relative] = path
            for violation in _path_violations(repo_relative, release=False):
                errors.append(f"Docker context {context_rel}: {violation}: {repo_relative}")
            try:
                detectors = _secret_detectors(path.read_bytes())
            except OSError:
                errors.append(f"Docker context {context_rel}: unreadable: {repo_relative}")
                continue
            for detector in detectors:
                errors.append(f"Docker context {context_rel}: secret-{detector}: {repo_relative}")
    print(f"OK Docker transmitted context: {context_rel} ({len(transmitted)} files)")
    return transmitted


def check_docker() -> None:
    errors: list[str] = []
    all_candidates: set[str] = set()
    context_ignores = {
        ".": ROOT / ".dockerignore",
        "backend": ROOT / "backend/.dockerignore",
        "frontend": ROOT / "frontend/.dockerignore",
    }
    transmitted_by_context: dict[str, dict[str, Path]] = {}
    used_by_context: dict[str, set[str]] = {key: set() for key in context_ignores}
    for context_rel, ignore in context_ignores.items():
        if not ignore.is_file():
            errors.append(f"缺少 default-deny Docker ignore：{_repo_relative(ignore)}")
            continue
        context = (ROOT / context_rel).resolve()
        transmitted_by_context[context_rel] = _context_transmitted_files(
            context,
            context_rel,
            ignore,
            errors,
        )

    for dockerfile_rel, context_rel in DOCKER_TARGETS:
        dockerfile = ROOT / dockerfile_rel
        context = (ROOT / context_rel).resolve()
        transmitted = transmitted_by_context.get(context_rel, {})
        candidates: dict[str, Path] = {}
        try:
            try:
                dockerfile_in_context = dockerfile.resolve().relative_to(context).as_posix()
            except ValueError:
                dockerfile_in_context = ""
            if dockerfile_in_context in transmitted:
                used_by_context[context_rel].add(dockerfile_in_context)
            for source in _read_copy_sources(dockerfile):
                expanded = _expand_copy_source(context, source, set(transmitted))
                if not expanded:
                    raise BoundaryError(f"COPY source 被 .dockerignore 完全排除：{source}")
                for path in expanded:
                    context_relative = path.relative_to(context).as_posix()
                    used_by_context[context_rel].add(context_relative)
                    candidates[_repo_relative(path)] = path
        except BoundaryError as exc:
            errors.append(f"{dockerfile_rel}: {exc}")
            continue
        for relative, path in candidates.items():
            all_candidates.add(relative)
            for violation in _path_violations(relative, release=False):
                errors.append(f"{dockerfile_rel}: {violation}: {relative}")
        print(f"OK Docker COPY candidates: {dockerfile_rel} ({len(candidates)} files)")

    for context_rel, transmitted in transmitted_by_context.items():
        unexpected = sorted(set(transmitted) - used_by_context[context_rel])
        for relative in unexpected:
            repo_relative = relative if context_rel == "." else f"{context_rel}/{relative}"
            errors.append(f"Docker context 传输了未被 COPY allowlist 使用的文件：{repo_relative}")

    prod_dockerfile = (ROOT / "docker/Dockerfile.backend.prod").read_text(encoding="utf-8")
    frontend_prod_dockerfile = (ROOT / "docker/Dockerfile.frontend.prod").read_text(encoding="utf-8")
    postgres_prod_dockerfile = (ROOT / "docker/Dockerfile.postgres.prod").read_text(encoding="utf-8")
    nginx_config = (ROOT / "docker/nginx.conf").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    dev_compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    entrypoint = (ROOT / "backend/scripts/container_entrypoint.py").read_text(encoding="utf-8")
    vite_config = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    ci_workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    prod_smoke = (ROOT / "scripts/prod_smoke.sh").read_text(encoding="utf-8")
    if not prod_dockerfile.startswith(
        "FROM python:3.12.13-alpine3.24@sha256:"
        "6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df\n"
    ):
        errors.append("production backend 未固定到已审计的 Python 3.12 / Alpine 3.24 基线")
    if "pip install --no-cache-dir --only-binary=:all: -r requirements.lock" not in prod_dockerfile:
        errors.append("production backend 未强制仅安装预编译 wheel")
    if "apt-get" in prod_dockerfile or "curl" in prod_dockerfile:
        errors.append("production backend 不得引入 Debian 包管理器或 curl 运行时依赖")
    if "addgroup -S vela" not in prod_dockerfile or "adduser -S -D -H -h /app -G vela vela" not in prod_dockerfile:
        errors.append("production backend 未使用 Alpine 非 root 账号")
    if not postgres_prod_dockerfile.startswith(
        "FROM postgres:16.14-alpine3.24@sha256:"
        "57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777\n"
    ):
        errors.append("production PostgreSQL 未固定到已审计的官方多架构摘要")
    for marker in (
        "apk add --no-cache su-exec=0.3-r0",
        "test -x /sbin/su-exec",
        "rm -f /usr/local/bin/gosu /usr/local/bin/su-exec",
        'test "$(grep -Fc \'exec gosu postgres',
        "sed -i 's|exec gosu postgres",
        'test "$(grep -Fc \'exec /sbin/su-exec postgres',
        "! grep -Fq 'exec gosu postgres",
        'bash -n "$entrypoint"',
        "test ! -e /usr/local/bin/gosu && test ! -L /usr/local/bin/gosu",
        "test ! -e /usr/local/bin/su-exec && test ! -L /usr/local/bin/su-exec",
        'test "$(/sbin/su-exec postgres id -u)" = \'70\'',
        'test "$(/sbin/su-exec postgres id -g)" = \'70\'',
        "'/var/lib/postgresql'",
    ):
        if marker not in postgres_prod_dockerfile:
            errors.append(f"production PostgreSQL 缺少 gosu 替换控制：{marker}")
    if "ln -s /sbin/su-exec" in postgres_prod_dockerfile:
        errors.append("production PostgreSQL 不得重建会保留旧 Go 元数据的 gosu 路径")
    if "ENV SEED_DEMO_USERS" in prod_dockerfile:
        errors.append("production image 不得暴露固定口令 demo seed 开关")
    if "seed_demo_user.py" in prod_dockerfile:
        errors.append("production image 不得携带固定口令 demo seed 脚本")
    if 'CMD ["python", "-m", "scripts.container_entrypoint"]' not in prod_dockerfile:
        errors.append("production image 未使用 fail-closed Python entrypoint")
    if "COPY scripts/__init__.py scripts/container_entrypoint.py scripts/create_user.py ./scripts/" not in prod_dockerfile:
        errors.append("production image 未把 entrypoint 作为可导入模块打包")
    if "python scripts/container_entrypoint.py" in prod_smoke:
        errors.append("production Compose smoke 不得以破坏 app 导入路径的文件方式运行 entrypoint")
    if "python -m scripts.container_entrypoint" not in prod_smoke:
        errors.append("production Compose smoke 未以模块方式运行 migration check")
    if '"${COMPOSE[@]}" cp ' in prod_smoke:
        errors.append("production Compose smoke 不得向只读容器根文件系统复制测试脚本")
    if 'exec -T backend env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app python -' not in prod_smoke or (
        '< "$ROOT/backend/scripts/seed_demo_user.py"' not in prod_smoke
    ):
        errors.append("production Compose smoke 未通过标准输入向只读后端注入一次性测试脚本")
    if "COPY alembic.ini ./" not in prod_dockerfile or "COPY alembic ./alembic" not in prod_dockerfile:
        errors.append("production image 未携带 Alembic 配置与迁移")
    if '"alembic"' not in entrypoint or '"upgrade"' not in entrypoint or '"head"' not in entrypoint:
        errors.append("production entrypoint 未在 Web 启动前执行 Alembic upgrade head")
    if 'mode == "check"' not in entrypoint or '"check"' not in entrypoint:
        errors.append("production entrypoint 缺少只读 migration head / schema drift 检查模式")
    if "VELA_ENTRYPOINT_MODE: migrate" not in compose:
        errors.append("production compose 缺少一次性 migration service")
    if "service_completed_successfully" not in compose:
        errors.append("production Web 未等待 migration service 成功")
    if "SEED_DEMO_USERS" in entrypoint or "SEED_DEMO_USERS:" in compose:
        errors.append("production startup path 不得包含固定口令 demo seed 开关")
    if "vela_change_me" in compose or "POSTGRES_PASSWORD:-" in compose:
        errors.append("production compose 仍包含数据库密码默认值")
    if "POSTGRES_PASSWORD:?set POSTGRES_PASSWORD" not in compose:
        errors.append("production compose 未强制要求数据库密码")
    if "DATABASE_URL:" in compose:
        errors.append("production compose 不得直接拼接 DATABASE_URL")
    if 'quote(database_password, safe="")' not in entrypoint:
        errors.append("production entrypoint 未 URL-encode 数据库密码")
    if '_required("SECRET_KEY")' not in entrypoint or "is_weak_secret(secret_key, min_length=32" not in entrypoint:
        errors.append("production entrypoint 未 fail-closed 校验 SECRET_KEY")
    if '_required("POSTGRES_PASSWORD")' not in entrypoint:
        errors.append("production entrypoint 未 fail-closed 校验数据库密码")
    if "127.0.0.1:${HTTP_PORT:-8080}:8080" not in compose:
        errors.append("production compose 默认 HTTP bind address 未限制在 loopback")
    if "dockerfile: docker/Dockerfile.postgres.prod" not in compose:
        errors.append("production compose 未使用已扫描的 PostgreSQL 包装镜像")
    if "image: postgres:" in compose:
        errors.append("production compose 不得绕过已扫描的 PostgreSQL 包装镜像")
    if "http.client.HTTPConnection('127.0.0.1', 8000, timeout=4)" not in compose:
        errors.append("production backend 健康检查未使用镜像内置 Python 标准库")
    if '["CMD", "curl"' in compose:
        errors.append("production backend 健康检查不得要求 curl")
    frontend_block = compose.split("\n  frontend:\n", 1)[-1].split("\nvolumes:\n", 1)[0]
    for marker, message in (
        ("read_only: true", "production frontend 根文件系统未设为只读"),
        ("cap_drop:", "production frontend 未移除 Linux capabilities"),
        ("- ALL", "production frontend 未移除全部 Linux capabilities"),
        ("no-new-privileges:true", "production frontend 未禁止提权"),
        ("/tmp:rw,noexec,nosuid,size=192m", "production frontend 临时文件系统不足以承载 100 MiB 上传缓冲"),
    ):
        if marker not in frontend_block:
            errors.append(message)
    if "USER nginx" not in frontend_prod_dockerfile:
        errors.append("production frontend image 未以 nginx 非 root 用户运行")
    if "EXPOSE 8080" not in frontend_prod_dockerfile or "listen 8080;" not in nginx_config:
        errors.append("production frontend 未使用非特权 8080 端口")
    if "pid /tmp/nginx.pid" not in frontend_prod_dockerfile:
        errors.append("production frontend 未把 Nginx PID 写入只读根文件系统之外")
    if not frontend_prod_dockerfile.startswith(
        "FROM node:24-alpine@sha256:"
        "a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS build\n"
    ):
        errors.append("production frontend build 未固定到已审计的 Node 24 Alpine 摘要")
    if (
        "FROM nginx:1.30.4-alpine@sha256:"
        "59d10bca5c674965ef4ff884715000dd60ef5567c36663523f108eec8e4105d4\n"
    ) not in frontend_prod_dockerfile:
        errors.append("production frontend runtime 未固定到已审计的 Nginx 1.30.4 Alpine 摘要")
    for marker in (
        "old_pid_pattern='^[[:space:]]*pid[[:space:]]+/run/nginx\\.pid;[[:space:]]*$'",
        "test \"$(grep -Ec \"$old_pid_pattern\" \"$main_config\")\" = '1'",
        'sed -Ei "s|$old_pid_pattern|pid /tmp/nginx.pid;|"',
        "test \"$(grep -Ec \"$new_pid_pattern\" \"$main_config\")\" = '1'",
        "! grep -Eq \"$old_pid_pattern\"",
        "test \"$(grep -Fc 'proxy_pass http://backend:8000/api/;' \"$server_config\")\" = '1'",
        'server_config_sha256="$(sha256sum "$server_config")"',
        'cp -p "$server_config" /tmp/default.conf.runtime',
        "sed -i 's|proxy_pass http://backend:8000/api/;|proxy_pass http://127.0.0.1:8000/api/;|'",
        "nginx -t",
        'mv /tmp/default.conf.runtime "$server_config"',
        'test "$(sha256sum "$server_config")" = "$server_config_sha256"',
        'CMD ["nginx", "-g", "daemon off;"]',
    ):
        if marker not in frontend_prod_dockerfile:
            errors.append(f"production frontend 缺少单一 PID / 配置语法控制：{marker}")
    if "daemon off; pid " in frontend_prod_dockerfile:
        errors.append("production frontend 不得在 -g 与 nginx.conf 重复定义 pid")
    for marker in ("proxy_read_timeout 180s;", "proxy_send_timeout 180s;", "client_body_timeout 180s;"):
        if marker not in nginx_config:
            errors.append(f"production Nginx 缺少上传/生成长请求边界：{marker}")
    if "DEPLOYMENT_MODE: single_tenant" not in compose:
        errors.append("production compose 未固定 single_tenant 受控试点边界")
    if "INSTANCE_ORGANIZATION: ${INSTANCE_ORGANIZATION:?" not in compose:
        errors.append("production compose 未强制绑定唯一试点组织")
    if 'CORPUS_AGENT_ENABLED: "false"' not in compose:
        errors.append("production compose 未关闭 Web 进程 corpus agent")
    if 'LLM_POLISH_ENABLED: "false"' not in compose:
        errors.append("production compose 未关闭受控试点 LLM polish")
    if 'SSO_ENABLED: ${SSO_ENABLED:-false}' not in compose:
        errors.append("production compose 未默认关闭未审计 SSO")
    if 'ALLOW_OPEN_REGISTRATION: ${ALLOW_OPEN_REGISTRATION:-false}' not in compose:
        errors.append("production compose 未默认关闭开放注册")
    if 'RATE_LIMIT_ENABLED: "true"' not in compose:
        errors.append("production compose 未启用认证速率限制")
    if '"--workers",\n        "1"' not in entrypoint:
        errors.append("production Web 进程未固定为单 worker")
    if '"127.0.0.1:8000:8000"' not in dev_compose or '"127.0.0.1:5173:5173"' not in dev_compose:
        errors.append("development compose 端口未限制在 loopback")
    if "env.VITE_API_PROXY || 'http://127.0.0.1:8000'" not in vite_config:
        errors.append("Vite dev proxy 未读取 VITE_API_PROXY")
    if "production-compose-smoke:" not in ci_workflow or "bash scripts/prod_smoke.sh" not in ci_workflow:
        errors.append("CI 缺少真实生产镜像、PostgreSQL migration 与 Compose smoke")
    if "docker build --pull -f docker/Dockerfile.postgres.prod -t vela-postgres:ci ." not in ci_workflow:
        errors.append("CI 未构建已移除扫描命中 gosu 的 PostgreSQL 镜像")
    if ci_workflow.count("image-ref: vela-postgres:ci") < 2:
        errors.append("CI 未对最终 PostgreSQL 包装镜像执行漏洞扫描和 SBOM")
    if "db_pid1_uid=" not in prod_smoke or "/proc/1/status" not in prod_smoke:
        errors.append("production Compose smoke 未验证 PostgreSQL PID 1 已降权")
    if "logs --no-color --tail=200" not in prod_smoke or "ps --all" not in prod_smoke:
        errors.append("production Compose smoke 失败时未保留服务状态与末尾日志")
    if "npm run test:e2e" not in prod_smoke or "playwright install --with-deps chromium" not in ci_workflow:
        errors.append("生产 Compose smoke 未用真实浏览器覆盖构建后的 SPA 登录路径")
    if "VELA_ENTRYPOINT_MODE=check" not in prod_smoke:
        errors.append("生产 Compose smoke 未在真实 PostgreSQL 上断言 migration head 与 schema drift")
    if 'VELA_API="http://127.0.0.1:${SMOKE_PORT}/api/v1" bash scripts/verify_e2e.sh' not in prod_smoke:
        errors.append("生产 Compose smoke 未在真实 PostgreSQL 上执行完整业务/法务 API 金路径")
    action_references = re.findall(r"(?m)^\s*(?:-\s+)?uses:\s+([^\s#]+)", ci_workflow)
    unpinned_actions = sorted(
        reference
        for reference in action_references
        if not reference.startswith("./")
        and not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", reference)
    )
    if unpinned_actions:
        errors.append(
            "CI 外部 Actions 必须固定到完整 commit SHA：" + ", ".join(unpinned_actions)
        )
    if "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25" not in ci_workflow:
        errors.append("CI 缺少固定 SHA 的 Trivy v0.36.0 容器安全扫描")
    if ci_workflow.count("format: cyclonedx") < 3:
        errors.append("CI 未为 backend/frontend/PostgreSQL 生产镜像生成 CycloneDX SBOM")
    if ci_workflow.count("severity: CRITICAL,HIGH") < 3 or ci_workflow.count('exit-code: "1"') < 3:
        errors.append("CI 未对 backend/frontend/PostgreSQL 镜像 fail-closed 拦截 High/Critical 漏洞")

    if "backend/app/data/corpus_pending_review.json" in all_candidates:
        errors.append("pending corpus 出现在 Docker COPY 候选")
    if any(path.startswith("backend/app/capability_packs/fixtures/") for path in all_candidates):
        errors.append("Capability Pack test fixture 出现在 Docker COPY 候选")

    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        raise BoundaryError(f"Docker/release boundary check failed ({len(errors)} errors)")
    print("OK excluded from Docker candidates: pending corpus and Capability Pack test fixtures")
    print("OK actual Docker contexts exclude secrets, runtime data, caches, and backend tests")
    print(
        "OK GitHub Actions SHA pins: "
        f"{len(action_references)} uses, {len(set(action_references))} unique references"
    )


def _collect_package_files() -> dict[str, bytes]:
    selected: set[Path] = set()

    def add(relative: str) -> None:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise BoundaryError(f"allowlist 文件不存在或不是普通文件：{relative}")
        selected.add(path)

    for relative in (*ROOT_FILES, *EXPLICIT_RUNTIME_FILES, *PACKAGE_SCRIPTS):
        add(relative)

    for tree_rel in PACKAGE_TREES:
        tree = ROOT / tree_rel
        if not tree.is_dir() or tree.is_symlink():
            raise BoundaryError(f"allowlist 目录不存在或不安全：{tree_rel}")
        for path in sorted(tree.rglob("*")):
            if path.is_symlink():
                raise BoundaryError(f"allowlist 目录含符号链接：{_repo_relative(path)}")
            if not path.is_file():
                continue
            relative = _repo_relative(path)
            lower_relative = relative.lower()
            if (
                lower_relative in {item.lower() for item in FORBIDDEN_RELEASE_FILES}
                or any(
                    lower_relative.startswith(prefix.lower())
                    for prefix in FORBIDDEN_RELEASE_PREFIXES
                )
                or lower_relative.startswith("frontend/src/test/")
            ):
                continue
            if path.suffix.lower() not in PACKAGE_SUFFIXES:
                continue
            if lower_relative.endswith((".spec.ts", ".test.ts")):
                continue
            selected.add(path)

    files: dict[str, bytes] = {}
    errors: list[str] = []
    for path in sorted(selected):
        relative = _repo_relative(path)
        violations = _path_violations(relative, release=True)
        if violations:
            errors.append(f"{','.join(violations)}: {relative}")
            continue
        content = path.read_bytes()
        for detector in _secret_detectors(content):
            errors.append(f"secret-{detector}: {relative}")
        files[relative] = content
    if errors:
        for error in errors:
            print(f"ERROR package candidate: {error}", file=sys.stderr)
        raise BoundaryError(f"package allowlist check failed ({len(errors)} errors)")
    _validate_internal_markdown_links(files)
    return files


def _validate_internal_markdown_links(files: dict[str, bytes]) -> None:
    """Reject links that point at files omitted from the release allowlist."""
    available = set(files)
    errors: list[str] = []
    for relative, content in files.items():
        if not relative.lower().endswith(".md"):
            continue
        text = content.decode("utf-8", errors="replace")
        parent = Path(relative).parent
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            target_path = (parent / target).as_posix()
            normalized = Path(target_path)
            if normalized.is_absolute() or ".." in normalized.parts:
                # Resolve safe repo-relative ../ links without allowing escape.
                normalized_parts: list[str] = []
                escaped = False
                for part in normalized.parts:
                    if part in ("", "."):
                        continue
                    if part == "..":
                        if not normalized_parts:
                            escaped = True
                            break
                        normalized_parts.pop()
                    else:
                        normalized_parts.append(part)
                if escaped:
                    errors.append(f"markdown-link-escape: {relative} -> {raw_target}")
                    continue
                target_path = "/".join(normalized_parts)
            else:
                target_path = normalized.as_posix()
            target_path = target_path.removeprefix("./")
            if target_path not in available:
                errors.append(f"markdown-link-missing: {relative} -> {raw_target}")
    if errors:
        for error in errors:
            print(f"ERROR package candidate: {error}", file=sys.stderr)
        raise BoundaryError(f"package Markdown link check failed ({len(errors)} errors)")


def _zip_info(relative: str, mode: int = 0o644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | mode) << 16
    return info


def _validated_output_path(output: Path) -> Path:
    expanded = output.expanduser()
    if expanded.suffix.lower() != ".zip":
        raise BoundaryError("submission output 必须使用 .zip 后缀")
    if expanded.is_symlink():
        raise BoundaryError("submission output 不得为符号链接")
    parent = expanded.parent
    if not parent.exists() or not parent.is_dir():
        raise BoundaryError("submission output 父目录必须是已存在的真实目录")
    parent = parent.resolve(strict=True)
    resolved = parent / expanded.name
    if resolved.exists() and not resolved.is_file():
        raise BoundaryError("submission output 已存在且不是普通文件")
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise BoundaryError("submission output 必须位于仓库外")
    return resolved


def _write_sha256_sidecar(output: Path) -> tuple[str, Path]:
    """Atomically publish a checksum sidecar for an already-built ZIP."""
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    sidecar = output.with_name(f"{output.name}.sha256")
    descriptor, temporary_sidecar_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp.sha256",
    )
    temporary_sidecar = Path(temporary_sidecar_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"{digest}  {output.name}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_sidecar, sidecar)
        sidecar.chmod(0o644)
    finally:
        if temporary_sidecar.exists():
            temporary_sidecar.unlink()
    return digest, sidecar


def build_package(output: Path) -> None:
    files = _collect_package_files()
    manifest = "".join(f"{hashlib.sha256(content).hexdigest()}  {relative}\n" for relative, content in files.items())
    files["SUBMISSION_MANIFEST.sha256"] = manifest.encode("utf-8")

    output = _validated_output_path(output)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.stem}.",
        suffix=".tmp.zip",
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, content in sorted(files.items()):
                mode = 0o755 if relative.endswith(".sh") or relative == "scripts/release_safety.py" else 0o644
                archive.writestr(_zip_info(relative, mode=mode), content)
        scan_package(temporary)
        os.replace(temporary, output)
        output.chmod(0o644)
    finally:
        if temporary.exists():
            temporary.unlink()
    digest, sidecar = _write_sha256_sidecar(output)
    print(f"OK submission ZIP: {output}")
    print(f"OK SHA-256 sidecar: {sidecar}")
    print(f"OK entries: {len(files)}; sha256: {digest}")


def _scan_embedded_archive(
    label: str,
    content: bytes,
    *,
    depth: int,
    state: dict[str, int],
    errors: list[str],
) -> None:
    buffer = io.BytesIO(content)
    if not zipfile.is_zipfile(buffer):
        return
    if depth >= MAX_ARCHIVE_DEPTH:
        errors.append(f"nested-archive-depth-limit: {label}")
        return
    buffer.seek(0)
    try:
        with zipfile.ZipFile(buffer, "r") as nested:
            for info in nested.infolist():
                state["entries"] += 1
                state["bytes"] += info.file_size
                nested_label = f"{label}!{info.filename}"
                if state["entries"] > MAX_ARCHIVE_ENTRIES:
                    errors.append(f"nested-archive-entry-limit: {label}")
                    return
                if (
                    info.file_size > MAX_ARCHIVE_ENTRY_BYTES
                    or state["bytes"] > MAX_ARCHIVE_TOTAL_BYTES
                ):
                    errors.append(f"nested-archive-size-limit: {nested_label}")
                    return
                for violation in _path_violations(info.filename, release=False):
                    errors.append(f"nested-{violation}: {nested_label}")
                mode = info.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if stat.S_ISLNK(mode) or (
                    file_type and not stat.S_ISREG(mode) and not stat.S_ISDIR(mode)
                ):
                    errors.append(f"nested-nonregular-entry: {nested_label}")
                    continue
                if info.flag_bits & 0x1:
                    errors.append(f"nested-encrypted-entry: {nested_label}")
                    continue
                if info.is_dir():
                    continue
                try:
                    nested_content = nested.read(info)
                except (RuntimeError, OSError, zipfile.BadZipFile):
                    errors.append(f"nested-unreadable-entry: {nested_label}")
                    continue
                for detector in _secret_detectors(nested_content):
                    errors.append(f"nested-secret-{detector}: {nested_label}")
                _scan_embedded_archive(
                    nested_label,
                    nested_content,
                    depth=depth + 1,
                    state=state,
                    errors=errors,
                )
    except (OSError, zipfile.BadZipFile):
        errors.append(f"invalid-nested-archive: {label}")


def scan_package(archive_path: Path) -> None:
    archive_path = archive_path.expanduser().resolve()
    errors: list[str] = []
    seen: set[str] = set()
    contents: dict[str, bytes] = {}
    archive_state = {"entries": 0, "bytes": 0}
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for info in archive.infolist():
                relative = PurePosixPath(info.filename).as_posix()
                for violation in _path_violations(info.filename, release=True):
                    errors.append(f"{violation}: {relative}")
                if relative in seen:
                    errors.append(f"duplicate-entry: {relative}")
                    continue
                seen.add(relative)
                mode = info.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if stat.S_ISLNK(mode) or (file_type and not stat.S_ISREG(mode) and not stat.S_ISDIR(mode)):
                    errors.append(f"nonregular-entry: {relative}")
                    continue
                if info.is_dir():
                    errors.append(f"directory-entry-not-allowed: {relative}")
                    continue
                if info.flag_bits & 0x1:
                    errors.append(f"encrypted-entry: {relative}")
                    continue
                archive_state["entries"] += 1
                archive_state["bytes"] += info.file_size
                if (
                    archive_state["entries"] > MAX_ARCHIVE_ENTRIES
                    or info.file_size > MAX_ARCHIVE_ENTRY_BYTES
                    or archive_state["bytes"] > MAX_ARCHIVE_TOTAL_BYTES
                ):
                    errors.append(f"archive-size-or-entry-limit: {relative}")
                    continue
                try:
                    content = archive.read(info)
                except (RuntimeError, OSError, zipfile.BadZipFile):
                    errors.append(f"unreadable-entry: {relative}")
                    continue
                contents[relative] = content
                for detector in _secret_detectors(content):
                    errors.append(f"secret-{detector}: {relative}")
                _scan_embedded_archive(
                    relative,
                    content,
                    depth=0,
                    state=archive_state,
                    errors=errors,
                )
    except (OSError, zipfile.BadZipFile) as exc:
        raise BoundaryError(f"无法读取 submission ZIP：{archive_path.name}") from exc

    allowlisted_names = set(_collect_package_files()) | {"SUBMISSION_MANIFEST.sha256"}
    for relative in sorted(set(contents) - allowlisted_names):
        errors.append(f"not-in-package-allowlist: {relative}")
    for relative in sorted(allowlisted_names - set(contents)):
        errors.append(f"missing-allowlisted-entry: {relative}")

    required = {
        "SUBMISSION_MANIFEST.sha256",
        "backend/app/capability_packs/brazil_new_energy_greenfield/manifest.json",
        "docs/RELEASE_CANDIDATE.md",
        "docker/Dockerfile.backend.prod",
        "frontend/src/main.ts",
        "scripts/check_release_boundaries.sh",
        "scripts/fixtures/sample_storage_project.txt",
    }
    for relative in sorted(required - contents.keys()):
        errors.append(f"missing-required-entry: {relative}")

    manifest_content = contents.get("SUBMISSION_MANIFEST.sha256", b"")
    try:
        manifest_lines = manifest_content.decode("utf-8").splitlines()
        expected = {}
        for line in manifest_lines:
            digest, relative = line.split("  ", 1)
            if relative in expected or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError
            expected[relative] = digest
        actual_names = set(contents) - {"SUBMISSION_MANIFEST.sha256"}
        if set(expected) != actual_names:
            errors.append("manifest-entry-set-mismatch")
        for relative in sorted(actual_names & set(expected)):
            if hashlib.sha256(contents[relative]).hexdigest() != expected[relative]:
                errors.append(f"manifest-hash-mismatch: {relative}")
    except (UnicodeDecodeError, ValueError):
        errors.append("invalid-submission-manifest")

    if errors:
        for error in errors:
            print(f"ERROR ZIP scan: {error}", file=sys.stderr)
        raise BoundaryError(f"submission ZIP scan failed ({len(errors)} errors)")
    demo_samples = sum(name.startswith("scripts/fixtures/") for name in contents)
    capability_fixtures = sum(name.startswith("backend/app/capability_packs/fixtures/") for name in contents)
    print(
        f"OK ZIP scan: {archive_path} ({len(contents)} files; "
        f"allowlisted demo samples={demo_samples}; capability test fixtures={capability_fixtures}; "
        "no user uploads, forbidden entries, or detected secrets)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check-docker", help="check Docker COPY candidates and production defaults")
    build = subparsers.add_parser("build-package", help="build and scan the allowlist submission ZIP")
    build.add_argument("output", type=Path)
    scan = subparsers.add_parser("scan-package", help="scan an existing submission ZIP")
    scan.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "check-docker":
            check_docker()
        elif args.command == "build-package":
            build_package(args.output)
        else:
            scan_package(args.archive)
    except BoundaryError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
