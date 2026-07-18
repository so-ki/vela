from __future__ import annotations

from types import SimpleNamespace

from app.services.brief_generator import (
    _executive_summary_pt,
    _executive_summary_zh,
    _retrieved_source_names,
)
from app.services.legal_rag import _retrieval_disclaimer


def _scenario():
    return SimpleNamespace(
        project_name="圣保罗工厂",
        industry="new-energy-manufacturing",
        action_type="greenfield",
    )


def test_executive_summary_discloses_only_sources_in_frozen_hits():
    sections = [
        {
            "items": [
                {
                    "legal_hits": [
                        {
                            "source": "alesp",
                            "source_label": "圣保罗州议会官方立法库",
                        },
                        {
                            "source": "alesp",
                            "source_label": "圣保罗州议会官方立法库",
                        },
                        {
                            "source": "planalto-legislacao",
                            "source_label": "Planalto 立法",
                        },
                    ]
                }
            ]
        }
    ]

    names_zh, names_pt = _retrieved_source_names(sections)
    summary_zh = _executive_summary_zh(_scenario(), {}, 1, 0, names_zh)
    summary_pt = _executive_summary_pt(_scenario(), {}, 1, 0, names_pt)

    assert names_zh == ["圣保罗州议会官方立法库", "Planalto 立法"]
    assert names_pt == [
        "Assembleia Legislativa do Estado de São Paulo (ALESP)",
        "Portal da Legislação do Planalto",
    ]
    assert "STF" not in summary_zh
    assert "STJ" not in summary_zh
    assert "STF" not in summary_pt
    assert "STJ" not in summary_pt
    assert "圣保罗州议会官方立法库、Planalto 立法" in summary_zh
    assert "Assembleia Legislativa do Estado de São Paulo (ALESP)" in summary_pt


def test_executive_summary_truthfully_states_when_no_source_was_returned():
    names_zh, names_pt = _retrieved_source_names([{"items": [{"legal_hits": []}]}])

    summary_zh = _executive_summary_zh(_scenario(), {}, 0, 1, names_zh)
    summary_pt = _executive_summary_pt(_scenario(), {}, 0, 1, names_pt)

    assert "未返回可列示法源" in summary_zh
    assert "não retornou fontes" in summary_pt
    assert "LexML/STF/STJ" not in summary_zh
    assert "LexML/STF/STJ" not in summary_pt


def test_retrieval_disclaimer_uses_actual_hit_sources_and_deduplicates_them():
    sections = [
        {
            "items": [
                {
                    "legal_hits": [
                        {"source": "alesp", "source_label": "圣保罗州议会官方立法库"},
                        {"source": "alesp", "source_label": "圣保罗州议会官方立法库"},
                    ]
                }
            ]
        }
    ]

    disclaimer = _retrieval_disclaimer(sections, match_threshold=70)

    assert disclaimer.count("圣保罗州议会官方立法库") == 1
    assert "LexML" not in disclaimer
    assert "STF" not in disclaimer
    assert "STJ" not in disclaimer
    assert "低于 70 分" in disclaimer


def test_retrieval_disclaimer_does_not_invent_sources_for_zero_hits():
    disclaimer = _retrieval_disclaimer(
        [{"items": [{"legal_hits": []}]}], match_threshold=70
    )

    assert "未命中可列示法源" in disclaimer
    assert "未命中不代表不存在相关法律要求" in disclaimer
