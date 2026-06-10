from app.services.document_extractor import _scan_or_empty_warning, extract_facts_from_document


def test_scan_or_empty_short_text():
    flag, warning = _scan_or_empty_warning("abc")
    assert flag is True
    assert warning


def test_scan_or_empty_normal_text():
    text = "计划在坎皮纳斯建设工业级储能系统组装工厂，约120名本地雇员。" * 3
    flag, warning = _scan_or_empty_warning(text)
    assert flag is False
    assert warning is None


def test_extract_empty_pdf_bytes():
    # Minimal invalid/empty content triggers failed extract without raising
    result = extract_facts_from_document("scan.pdf", b"%PDF-1.4\n")
    assert result.get("scan_or_empty") or result.get("extraction_warning") or result.get("mode") == "failed"
