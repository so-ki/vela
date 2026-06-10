"""Tests for shared grounding utilities."""

from app.services.grounding_utils import (
    char_overlap,
    is_boilerplate_phrase,
    normalize_text,
    verify_snippet_in_source,
)


def test_normalize_text_collapses_whitespace():
    assert normalize_text("  Foo\nBar  ") == "foo bar"


def test_char_overlap_exact_substring():
    hay = "decreto-lei 5452 consolidação das leis do trabalho art 7"
    assert char_overlap("consolidação das leis", hay) == 1.0


def test_char_overlap_partial():
    score = char_overlap("local employees about 450", "creates about 450 local jobs in campinas")
    assert 0.0 < score < 1.0


def test_verify_snippet_exact_match():
    source = "创造约450名新的就业岗位，按 CLT 雇佣本地员工。"
    snippet = "创造约450名新的就业岗位"
    result = verify_snippet_in_source(snippet, source)
    assert result["grounded"] is True
    assert result["grounding_score"] >= 0.55
    assert result["citation_status"] == "corpus_verified"


def test_verify_snippet_empty_excerpt():
    result = verify_snippet_in_source("", "some source text")
    assert result["grounded"] is False
    assert result["grounding_score"] == 0.0
    assert result["citation_status"] == "ungrounded"


def test_boilerplate_phrase_detected():
    assert is_boilerplate_phrase("不构成正式法律意见") is True
    assert is_boilerplate_phrase("CLT Art. 7 employee rights") is False


def test_verify_boilerplate_only_weak():
    source = "Lei 4131 foreign capital registration requirements."
    snippet = "不构成正式法律意见"
    result = verify_snippet_in_source(snippet, source)
    assert result["grounded"] is False
    assert result["citation_status"] in {"weak_grounding", "ungrounded"}
