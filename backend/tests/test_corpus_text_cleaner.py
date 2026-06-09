"""Tests for corpus text cleaning."""

from app.services.corpus_text_cleaner import clean_text_pt, excerpt_for_display, is_polluted


def test_is_polluted_detects_lexml_js():
    raw = "Lei 8036 :: Legislação:: var url = document.location.href"
    assert is_polluted(raw)


def test_clean_strips_garbage_and_keeps_title():
    raw = (
        "Decreto-Lei 5452 :: Legislação::Decreto-Lei 5452/1943 :: "
        "var url = document.location.href"
    )
    clean = clean_text_pt(
        raw,
        title_pt="Decreto-Lei nº 5.452/1943 - CLT",
        text_zh="劳动法 CLT",
    )
    assert "var url" not in clean
    assert "CLT" in clean
    assert "劳动法" not in clean


def test_excerpt_prefers_zh_summary():
    doc = {
        "title_pt": "Lei 13.709/2018 - LGPD",
        "title_zh": "LGPD",
        "text_pt": "Lei 13.709/2018 - LGPD",
        "text_zh": "巴西通用数据保护法摘要。",
    }
    excerpt_pt, excerpt_zh = excerpt_for_display(doc)
    assert excerpt_zh.startswith("巴西")
    assert "var url" not in excerpt_pt
