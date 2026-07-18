import json

import pytest

from app.packs import loader


@pytest.fixture(autouse=True)
def _clear_loader_cache():
    loader.clear_caches()
    yield
    loader.clear_caches()


def _write_pack(root, pack_id, manifest=None, cards=None):
    pack_dir = root / pack_id
    pack_dir.mkdir(parents=True)
    manifest = manifest or {"manifest_version": "0.1-draft", "pack_id": pack_id, "certification_status": "provisional"}
    (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if cards:
        cards_dir = pack_dir / "rule_cards"
        cards_dir.mkdir()
        for i, card in enumerate(cards):
            (cards_dir / f"card{i}.json").write_text(json.dumps(card), encoding="utf-8")
    return pack_dir


def test_empty_dir_lists_zero_packs(tmp_path):
    assert loader.list_installed_packs(root=tmp_path) == []


def test_load_manifest_missing_returns_none(tmp_path):
    assert loader.load_manifest("nope", root=tmp_path) is None


def test_require_manifest_missing_raises(tmp_path):
    with pytest.raises(loader.PackNotInstalledError):
        loader.require_manifest("nope", root=tmp_path)


def test_load_manifest_and_cards(tmp_path):
    _write_pack(tmp_path, "neutral_pack", cards=[{"rule_id": "XX-YY-001"}])
    manifest = loader.load_manifest("neutral_pack", root=tmp_path)
    assert manifest["pack_id"] == "neutral_pack"
    cards = loader.load_rule_cards("neutral_pack", root=tmp_path)
    assert len(cards) == 1


def test_installed_reference_pack_manifest_is_valid():
    """仓库自带的参考包 manifest 必须可加载且明确标注 provisional 与 draft。"""
    manifests = loader.list_installed_packs()
    assert manifests, "reference pack manifest missing"
    ref = manifests[0]
    assert ref["manifest_version"] == "0.1-draft"
    assert ref["certification_status"] == "provisional"
    assert ref["exclusions"], "manifest must state exclusions explicitly"
    assert ref["coverage_denominators"], "coverage denominators must be declared"
