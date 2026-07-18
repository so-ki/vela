from __future__ import annotations

import asyncio
import io
import os
import zipfile
from pathlib import Path

import pytest

import app.services.material_file_storage as material_storage
from app.services.document_extractor import read_upload_text
from app.services.upload_security import (
    MAX_BATCH_BYTES,
    MAX_BATCH_FILES,
    MAX_EXTRACTED_CHARACTERS,
    MAX_DELIVERY_EVIDENCE_BYTES_PER_INSTANCE,
    MAX_DELIVERY_EVIDENCE_BYTES_PER_USER,
    MAX_DELIVERY_EVIDENCE_OBJECTS_PER_INSTANCE,
    MAX_DELIVERY_EVIDENCE_OBJECTS_PER_USER,
    MAX_FILE_BYTES,
    MAX_PROJECT_DOCUMENTS,
    enforce_project_document_quota,
    read_evidence_upload_limited,
    read_upload_limited,
    validate_evidence_container,
    validate_upload_container,
)


class FakeUpload:
    def __init__(self, filename: str, chunks: list[bytes]):
        self.filename = filename
        self._chunks = iter(chunks)
        self.closed = False

    async def read(self, _size: int = -1) -> bytes:
        return next(self._chunks, b"")

    async def close(self) -> None:
        self.closed = True


def test_upload_limits_are_bounded_for_controlled_pilot():
    assert MAX_FILE_BYTES == 25 * 1024 * 1024
    assert MAX_BATCH_FILES == 10
    assert MAX_BATCH_BYTES == 100 * 1024 * 1024
    assert MAX_DELIVERY_EVIDENCE_OBJECTS_PER_USER == 500
    assert MAX_DELIVERY_EVIDENCE_BYTES_PER_USER == 1024 * 1024 * 1024
    assert MAX_DELIVERY_EVIDENCE_OBJECTS_PER_INSTANCE == 5_000
    assert MAX_DELIVERY_EVIDENCE_BYTES_PER_INSTANCE == 5 * 1024 * 1024 * 1024


def test_chunked_upload_is_rejected_before_all_chunks_are_consumed():
    upload = FakeUpload("note.txt", [b"1234", b"5678", b"should-not-be-read"])
    with pytest.raises(ValueError, match="不能超过"):
        asyncio.run(read_upload_limited(upload, max_bytes=5))
    assert upload.closed is True


def test_extension_and_magic_must_agree():
    with pytest.raises(ValueError, match="不是有效 PDF"):
        validate_upload_container("fake.pdf", b"this is not a PDF")


def test_delivery_evidence_upload_is_bounded_and_container_checked():
    upload = FakeUpload("report.json", [b'{"status":', b'"passed"}'])
    assert asyncio.run(read_evidence_upload_limited(upload)) == b'{"status":"passed"}'
    assert upload.closed is True

    with pytest.raises(ValueError, match="UTF-8 JSON"):
        validate_evidence_container("broken.json", b"{not-json}")
    with pytest.raises(ValueError, match="DTD"):
        validate_evidence_container(
            "external-entity.xml",
            b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>',
        )
    with pytest.raises(ValueError, match="主动内容"):
        validate_evidence_container("active.pdf", b"%PDF-1.7\n/OpenAction")
    validate_evidence_container("signature.p7s", b"opaque-pkcs7-container")


@pytest.mark.parametrize(
    "marker",
    [
        b"/JavaScript",
        b"/JS",
        b"/Launch",
        b"/EmbeddedFile",
        b"/EmbeddedFiles",
        b"/OpenAction",
        b"/AA",
        b"/XFA",
        b"/Java#53cript",
    ],
)
def test_pdf_active_content_is_rejected(marker: bytes):
    with pytest.raises(ValueError, match="主动内容"):
        validate_upload_container("active.pdf", b"%PDF-1.7\n1 0 obj << " + marker + b" >>")


@pytest.mark.parametrize(
    "safe_name",
    [b"/AATLFontDescriptor", b"/JSTextLabel", b"/JavaScriptEnabledLabel"],
)
def test_pdf_active_content_scanner_does_not_match_name_prefixes(safe_name: bytes):
    validate_upload_container("passive.pdf", b"%PDF-1.7\n1 0 obj << " + safe_name + b" >>")


def test_docx_embedded_object_is_rejected():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr("word/embeddings/oleObject1.bin", b"payload")
    with pytest.raises(ValueError, match="嵌入对象"):
        validate_upload_container("embedded.docx", out.getvalue())


def test_unsafe_filename_is_rejected():
    with pytest.raises(ValueError, match="文件名"):
        validate_upload_container("../material.txt", b"facts")


def test_docx_zip_bomb_ratio_is_rejected():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr("word/bomb.bin", b"0" * (2 * 1024 * 1024))
    with pytest.raises(ValueError, match="压缩比异常"):
        validate_upload_container("bomb.docx", out.getvalue())


def test_archived_material_is_private_and_symlink_safe(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(material_storage, "UPLOAD_ROOT", tmp_path / "materials")
    archived = material_storage.save_scenario_material_files(
        7,
        [("facts.txt", b"trusted pilot material", "text/plain")],
    )
    stored_name = archived[0]["stored_name"]
    assert archived[0]["content_screening"] == "active_content_screened_not_antivirus"
    path = material_storage.scenario_material_dir(7) / stored_name
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.stat(path.parent).st_mode & 0o777 == 0o700
    assert material_storage.resolve_archived_file_path(7, stored_name) == path.resolve()
    assert material_storage.resolve_archived_file_path(7, "../" + stored_name) is None

    link = path.parent / ("f" * 32 + "__link.txt")
    link.symlink_to(path)
    assert material_storage.resolve_archived_file_path(7, link.name) is None


def test_archived_material_has_project_and_instance_quotas(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(material_storage, "UPLOAD_ROOT", tmp_path / "materials")
    monkeypatch.setattr(material_storage, "MAX_SCENARIO_ARCHIVED_FILES", 1)
    monkeypatch.setattr(material_storage, "MAX_SCENARIO_ARCHIVED_BYTES", 5)
    monkeypatch.setattr(material_storage, "MAX_INSTANCE_ARCHIVED_BYTES", 8)

    material_storage.save_scenario_material_files(1, [("one.txt", b"1234", "text/plain")])
    with pytest.raises(ValueError, match="最多归档"):
        material_storage.save_scenario_material_files(1, [("two.txt", b"1", "text/plain")])
    with pytest.raises(ValueError, match="5GB"):
        material_storage.save_scenario_material_files(2, [("three.txt", b"12345", "text/plain")])


def test_plain_text_extraction_has_character_ceiling():
    oversized = b"a" * (MAX_EXTRACTED_CHARACTERS + 1)
    with pytest.raises(ValueError, match="安全上限"):
        read_upload_text("oversized.txt", oversized)


def test_project_embedded_document_count_and_character_quotas():
    payload = {
        "_contract_texts": {
            str(index): "x" for index in range(MAX_PROJECT_DOCUMENTS)
        }
    }
    with pytest.raises(ValueError, match="最多保存"):
        enforce_project_document_quota(payload, "new")

    payload = {"_contract_texts": {"one": "x" * 4_999_999}}
    with pytest.raises(ValueError, match="500 万字符"):
        enforce_project_document_quota(payload, "yy")
