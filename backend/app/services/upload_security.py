"""Bounded upload reading and lightweight container-signature validation."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_BATCH_FILES = 10
MAX_BATCH_BYTES = 100 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
MAX_ZIP_ENTRIES = 2_000
MAX_ZIP_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 100
MAX_EXTRACTED_CHARACTERS = 2_000_000
MAX_PROJECT_DOCUMENTS = 30
MAX_PROJECT_STORED_CHARACTERS = 5_000_000
ALLOWED_SUFFIXES = {".txt", ".md", ".docx", ".pdf"}
PDF_ACTIVE_CONTENT_NAMES = frozenset(
    {
        b"javascript",
        b"js",
        b"launch",
        b"embeddedfile",
        b"embeddedfiles",
        b"richmedia",
        b"openaction",
        b"aa",
        b"xfa",
    }
)
PDF_NAME_TOKEN_RE = re.compile(rb"/([^\x00\t\n\f\r ()<>\[\]{}/%]+)")
PDF_NAME_ESCAPE_RE = re.compile(rb"#([0-9a-fA-F]{2})")


def validate_upload_container(filename: str, content: bytes) -> None:
    if (
        not filename
        or len(filename.encode("utf-8")) > 512
        or Path(filename).name != filename
        or "\\" in filename
        or any(ord(char) < 32 or ord(char) == 127 for char in filename)
    ):
        raise ValueError("文件名不安全或过长")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"仅支持 {', '.join(sorted(ALLOWED_SUFFIXES))} 文件")
    if not content:
        raise ValueError("文件为空")
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("文件扩展名为 PDF，但内容不是有效 PDF")
    if suffix == ".pdf":
        if _pdf_has_active_content_name(content):
            raise ValueError("PDF 包含 JavaScript、启动动作、嵌入文件或其他主动内容")
    if suffix == ".docx":
        if not content.startswith(b"PK"):
            raise ValueError("文件扩展名为 DOCX，但内容不是有效 Office Open XML")
        _validate_docx_archive(content)
    if suffix in {".txt", ".md"} and b"\x00" in content[:4096]:
        raise ValueError("文本文件包含二进制空字节")


def _validate_docx_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise ValueError("DOCX 压缩包条目过多")
            names = {info.filename for info in infos}
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                raise ValueError("DOCX 缺少必要的 Office XML 部件")
            expanded = 0
            compressed = 0
            for info in infos:
                path = Path(info.filename)
                lower_name = info.filename.lower()
                if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                    raise ValueError("DOCX 包含不安全路径")
                if (
                    lower_name.endswith("vbaproject.bin")
                    or lower_name.startswith("word/activex/")
                    or lower_name.startswith("word/embeddings/")
                ):
                    raise ValueError("DOCX 包含宏、ActiveX 或嵌入对象")
                expanded += int(info.file_size)
                compressed += max(1, int(info.compress_size))
                if expanded > MAX_ZIP_EXPANDED_BYTES:
                    raise ValueError("DOCX 解压后体积超过 100MB")
            if expanded / max(1, compressed) > MAX_ZIP_COMPRESSION_RATIO:
                raise ValueError("DOCX 压缩比异常，疑似压缩炸弹")
            for info in infos:
                if not info.filename.lower().endswith(".rels"):
                    continue
                if info.file_size > 1024 * 1024:
                    raise ValueError("DOCX 关系文件异常过大")
                relationships = archive.read(info).lower()
                if b'targetmode="external"' in relationships and (
                    b"attachedtemplate" in relationships
                    or b"oleobject" in relationships
                    or b"/package" in relationships
                ):
                    raise ValueError("DOCX 包含外部模板或外部嵌入对象")
    except zipfile.BadZipFile as exc:
        raise ValueError("DOCX 压缩结构损坏") from exc


def _pdf_has_active_content_name(content: bytes) -> bool:
    """Match complete PDF name objects, including ``#xx`` escapes.

    A substring scan makes safe names such as ``/AATL...`` look like the
    dangerous additional-actions key ``/AA``. PDF names end at a delimiter,
    so compare decoded complete tokens instead. This is deliberately only a
    lightweight active-content screen, not an antivirus claim.
    """

    for match in PDF_NAME_TOKEN_RE.finditer(content):
        token = PDF_NAME_ESCAPE_RE.sub(
            lambda escaped: bytes([int(escaped.group(1), 16)]),
            match.group(1),
        ).lower()
        if token in PDF_ACTIVE_CONTENT_NAMES:
            return True
    return False


async def read_upload_limited(upload: Any, *, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await upload.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"单个文件不能超过 {max_bytes // (1024 * 1024)}MB")
            chunks.append(chunk)
    finally:
        close = getattr(upload, "close", None)
        if close is not None:
            await close()
    content = b"".join(chunks)
    validate_upload_container(getattr(upload, "filename", None) or "upload.bin", content)
    return content


async def read_uploads_limited(uploads: Iterable[Any]) -> list[tuple[str, bytes]]:
    items = list(uploads)
    if not items:
        raise ValueError("请至少上传一个文件")
    if len(items) > MAX_BATCH_FILES:
        raise ValueError(f"单次最多上传 {MAX_BATCH_FILES} 个文件")

    result: list[tuple[str, bytes]] = []
    total = 0
    for upload in items:
        content = await read_upload_limited(upload)
        total += len(content)
        if total > MAX_BATCH_BYTES:
            raise ValueError("所有文件合计不能超过 100MB")
        result.append((getattr(upload, "filename", None) or "upload.txt", content))
    return result


def enforce_project_document_quota(payload: dict[str, Any], new_text: str) -> None:
    """Bound document text embedded in the scenario JSON payload."""
    contract_texts = payload.get("_contract_texts") or {}
    diligence_texts = payload.get("_diligence_texts") or {}
    existing = [*contract_texts.values(), *diligence_texts.values()]
    if len(existing) >= MAX_PROJECT_DOCUMENTS:
        raise ValueError(f"单个项目最多保存 {MAX_PROJECT_DOCUMENTS} 份合同/尽调文档")
    total_chars = sum(len(str(text)) for text in existing) + len(new_text)
    if total_chars > MAX_PROJECT_STORED_CHARACTERS:
        raise ValueError("单个项目保存的合同/尽调正文合计不能超过 500 万字符")
