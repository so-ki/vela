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
    "backend/.dockerignore",
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
    "backend/scripts/container_entrypoint.py",
    "backend/scripts/seed_demo_user.py",
    "frontend/.dockerignore",
    "frontend/index.html",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "docker/Dockerfile.backend",
    "docker/Dockerfile.backend.prod",
    "docker/Dockerfile.frontend",
    "docker/Dockerfile.frontend.prod",
    "docker/nginx.conf",
)

PACKAGE_TREES = (
    "backend/app/api",
    "backend/app/core",
    "backend/app/models",
    "backend/app/schemas",
    "backend/app/services",
    "backend/app/capability_packs/brazil_new_energy_greenfield",
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
    ".md",
    ".opml",
    ".png",
    ".py",
    ".sh",
    ".svg",
    ".ts",
    ".vue",
    ".xmind",
}


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
    if release and (lower_normalized.endswith(".spec.ts") or lower_normalized.endswith(".test.ts")):
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
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    dev_compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    entrypoint = (ROOT / "backend/scripts/container_entrypoint.py").read_text(encoding="utf-8")
    vite_config = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    if "ENV SEED_DEMO_USERS=false" not in prod_dockerfile:
        errors.append("production demo seed 缺少默认关闭开关")
    if 'CMD ["python", "scripts/container_entrypoint.py"]' not in prod_dockerfile:
        errors.append("production image 未使用 fail-closed Python entrypoint")
    if 'os.environ.get("SEED_DEMO_USERS", "false")' not in entrypoint:
        errors.append("production demo seed 未受显式 true 条件保护")
    if "vela_change_me" in compose or "POSTGRES_PASSWORD:-" in compose:
        errors.append("production compose 仍包含数据库密码默认值")
    if "POSTGRES_PASSWORD:?set POSTGRES_PASSWORD" not in compose:
        errors.append("production compose 未强制要求数据库密码")
    if "DATABASE_URL:" in compose:
        errors.append("production compose 不得直接拼接 DATABASE_URL")
    if 'quote(database_password, safe="")' not in entrypoint:
        errors.append("production entrypoint 未 URL-encode 数据库密码")
    if '_required("SECRET_KEY")' not in entrypoint or "len(secret_key) < 32" not in entrypoint:
        errors.append("production entrypoint 未 fail-closed 校验 SECRET_KEY")
    if '_required("POSTGRES_PASSWORD")' not in entrypoint:
        errors.append("production entrypoint 未 fail-closed 校验数据库密码")
    if "SEED_DEMO_USERS: ${SEED_DEMO_USERS:-false}" not in compose:
        errors.append("production compose 未默认关闭 demo seed")
    if "${HTTP_BIND_ADDRESS:-0.0.0.0}:${HTTP_PORT:-8080}:80" not in compose:
        errors.append("production compose 未提供显式 HTTP bind address")
    if '"127.0.0.1:8000:8000"' not in dev_compose or '"127.0.0.1:5173:5173"' not in dev_compose:
        errors.append("development compose 端口未限制在 loopback")
    if "env.VITE_API_PROXY || 'http://127.0.0.1:8000'" not in vite_config:
        errors.append("Vite dev proxy 未读取 VITE_API_PROXY")

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
    return files


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
    finally:
        if temporary.exists():
            temporary.unlink()
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"OK submission ZIP: {output}")
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
