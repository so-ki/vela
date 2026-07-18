"""规则卡质量门：全部卡必须过 schema、标 provisional、法源可溯。"""

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

PACKS_DIR = Path(__file__).resolve().parents[1] / "app" / "packs"
SCHEMA = json.loads((PACKS_DIR / "rule_card.schema.json").read_text(encoding="utf-8"))
CARD_PATHS = sorted(PACKS_DIR.glob("*/rule_cards/*.json"))


def test_reference_pack_has_first_batch_of_cards():
    assert len(CARD_PATHS) >= 10


@pytest.mark.parametrize("card_path", CARD_PATHS, ids=lambda p: p.stem)
def test_card_validates_against_schema(card_path):
    card = json.loads(card_path.read_text(encoding="utf-8"))
    jsonschema.validate(card, SCHEMA)


@pytest.mark.parametrize("card_path", CARD_PATHS, ids=lambda p: p.stem)
def test_card_is_provisional_until_certified_reviewers_exist(card_path):
    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert card["certification_status"] == "provisional"


@pytest.mark.parametrize("card_path", CARD_PATHS, ids=lambda p: p.stem)
def test_card_elements_bind_fact_fields(card_path):
    card = json.loads(card_path.read_text(encoding="utf-8"))
    for element in card["elements"]:
        assert element["fact_fields"], f"{card['rule_id']}:{element['element_id']} 要件未挂事实字段"
