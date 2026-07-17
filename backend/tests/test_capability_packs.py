"""Capability Pack registry and loader contract tests.

Every damaged manifest/artifact is copied under ``tmp_path`` first.  These
tests must never mutate the server-owned production pack or its artifacts.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.capability_packs.loader import (
    CapabilityPackIntegrityError,
    CapabilityPackLoadError,
    CapabilityPackSchemaError,
)
from app.capability_packs.registry import (
    CAPABILITY_PACKS_ROOT,
    CapabilityPackFixtureDisabledError,
    CapabilityPackInactiveError,
    CapabilityPackNotFoundError,
    CapabilityPackRegistry,
    CapabilityPackUnsupportedError,
)


FORMAL_PACK_ID = "brazil_new_energy_greenfield"
FIXTURE_PACK_ID = "test_fixture_pack"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _isolated_formal_registry_root(tmp_path: Path) -> tuple[Path, Path]:
    """Copy only the formal manifest and its referenced artifacts."""

    app_root = tmp_path / "app"
    capability_root = app_root / "capability_packs"
    pack_root = capability_root / FORMAL_PACK_ID
    rules_root = app_root / "rules"
    data_root = app_root / "data"
    pack_root.mkdir(parents=True)
    rules_root.mkdir(parents=True)
    data_root.mkdir(parents=True)

    source_manifest = CAPABILITY_PACKS_ROOT / FORMAL_PACK_ID / "manifest.json"
    manifest = _read_json(source_manifest)
    shutil.copy2(source_manifest, pack_root / "manifest.json")
    shutil.copy2(
        CAPABILITY_PACKS_ROOT.parent / "rules" / manifest["rules_artifact"]["resource"].split("://", 1)[1],
        rules_root / manifest["rules_artifact"]["resource"].split("://", 1)[1],
    )
    shutil.copy2(
        CAPABILITY_PACKS_ROOT.parent / "data" / manifest["corpus_artifact"]["resource"].split("://", 1)[1],
        data_root / manifest["corpus_artifact"]["resource"].split("://", 1)[1],
    )
    return capability_root, pack_root / "manifest.json"


def test_production_registry_loads_formal_brazil_pack() -> None:
    registry = CapabilityPackRegistry(app_env="production")

    pack = registry.get(FORMAL_PACK_ID)

    assert pack.is_test_fixture is False
    assert pack.manifest.pack_id == FORMAL_PACK_ID
    assert pack.manifest.version == "1.3.0"
    assert pack.manifest.content_status == "provisional"
    assert pack.manifest.status == "active"
    assert pack.manifest.country == "BR"
    assert pack.manifest.state == "sao_paulo"
    assert pack.manifest.industry == "new_energy_manufacturing"
    assert pack.manifest.action_type == "greenfield_plant"
    assert pack.manifest.semantic_hash == pack.manifest.canonical_semantic_hash()
    assert pack.rules["pack"]["id"] == pack.manifest.rules_artifact.artifact_id
    assert pack.corpus["version"] == pack.manifest.corpus_artifact.version


def test_test_environment_explicitly_loads_fixture_but_public_list_hides_it() -> None:
    registry = CapabilityPackRegistry(app_env="test", include_test_fixtures=True)

    pack = registry.get(FIXTURE_PACK_ID)

    assert pack.is_test_fixture is True
    assert pack.manifest.display_name == "非真实测试能力包"
    assert registry.match(
        country="ZZ-TEST",
        state="ZZ-STATE",
        industry="fixture_industry",
        action_type="fixture_action",
    ).pack_id == FIXTURE_PACK_ID
    assert FIXTURE_PACK_ID not in {
        item["pack_id"] for item in registry.list_public_active()
    }


def test_production_rejects_fixture_enablement_and_does_not_discover_fixture() -> None:
    with pytest.raises(CapabilityPackFixtureDisabledError):
        CapabilityPackRegistry(app_env="production", include_test_fixtures=True)

    registry = CapabilityPackRegistry(app_env="production")
    with pytest.raises(CapabilityPackNotFoundError):
        registry.get(FIXTURE_PACK_ID)


def test_nonexistent_pack_is_rejected() -> None:
    registry = CapabilityPackRegistry(app_env="production")

    with pytest.raises(CapabilityPackNotFoundError):
        registry.get("missing_capability_pack")


def test_inactive_pack_is_rejected(tmp_path: Path) -> None:
    root, manifest_path = _isolated_formal_registry_root(tmp_path)
    manifest = _read_json(manifest_path)
    # status is deliberately excluded from generation semantic identity.
    manifest["status"] = "inactive"
    _write_json(manifest_path, manifest)
    registry = CapabilityPackRegistry(root=root, app_env="production")

    with pytest.raises(CapabilityPackInactiveError):
        registry.get(FORMAL_PACK_ID)
    assert registry.list_active() == []
    assert registry.get(FORMAL_PACK_ID, require_active=False).manifest.status == "inactive"


def test_manifest_schema_error_is_rejected(tmp_path: Path) -> None:
    root, manifest_path = _isolated_formal_registry_root(tmp_path)
    manifest = _read_json(manifest_path)
    manifest.pop("output_profile")
    _write_json(manifest_path, manifest)

    with pytest.raises(CapabilityPackSchemaError):
        CapabilityPackRegistry(root=root, app_env="production").get(FORMAL_PACK_ID)


def test_manifest_semantic_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    root, manifest_path = _isolated_formal_registry_root(tmp_path)
    manifest = _read_json(manifest_path)
    manifest["industry"] = "tampered_industry"
    _write_json(manifest_path, manifest)

    with pytest.raises(CapabilityPackIntegrityError, match="semantic hash"):
        CapabilityPackRegistry(root=root, app_env="production").get(FORMAL_PACK_ID)


def test_rules_artifact_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    root, manifest_path = _isolated_formal_registry_root(tmp_path)
    manifest = _read_json(manifest_path)
    rules_path = root.parent / "rules" / manifest["rules_artifact"]["resource"].split("://", 1)[1]
    rules = _read_json(rules_path)
    rules["pack"]["name"] = "tampered only in tmp_path"
    _write_json(rules_path, rules)

    with pytest.raises(CapabilityPackIntegrityError, match="rules artifact content hash"):
        CapabilityPackRegistry(root=root, app_env="production").get(FORMAL_PACK_ID)


@pytest.mark.parametrize(
    "resource",
    [
        "rules://../brazil_new_energy.json",
        "rules:///tmp/arbitrary.json",
    ],
)
def test_artifact_path_traversal_or_absolute_path_is_rejected(
    tmp_path: Path, resource: str
) -> None:
    root, manifest_path = _isolated_formal_registry_root(tmp_path)
    manifest = _read_json(manifest_path)
    manifest["rules_artifact"]["resource"] = resource
    _write_json(manifest_path, manifest)

    with pytest.raises((CapabilityPackSchemaError, CapabilityPackLoadError)):
        CapabilityPackRegistry(root=root, app_env="production").get(FORMAL_PACK_ID)


def test_registry_matches_formal_pack_by_route() -> None:
    registry = CapabilityPackRegistry(app_env="production")

    match = registry.match(
        country="br",
        state="SAO_PAULO",
        industry="NEW_ENERGY_MANUFACTURING",
        action_type="GREENFIELD_PLANT",
    )

    assert match.pack_id == FORMAL_PACK_ID


def test_unmatched_route_fails_without_brazil_fallback() -> None:
    registry = CapabilityPackRegistry(app_env="production")

    with pytest.raises(CapabilityPackUnsupportedError):
        registry.match(
            country="MX",
            state="nuevo_leon",
            industry="mining",
            action_type="acquisition",
        )


def test_material_match_requires_text_evidence_even_when_client_hints_claim_formal_route() -> None:
    registry = CapabilityPackRegistry(app_env="production")

    with pytest.raises(CapabilityPackUnsupportedError):
        registry.match_material(
            material_text="本项目拟在墨西哥收购铜矿企业并取得既有采矿权。",
            country_hint="BR",
            state_hint="sao_paulo",
            industry_hint="new_energy_manufacturing",
            action_type_hint="greenfield_plant",
        )


def test_short_country_code_does_not_match_inside_an_unrelated_word() -> None:
    registry = CapabilityPackRegistry(app_env="production")

    with pytest.raises(CapabilityPackUnsupportedError):
        registry.match_material(
            material_text="墨西哥项目：sobre 新能源 建设工厂",
        )


@pytest.mark.parametrize(
    "material_text",
    [
        "项目拟在巴西圣保罗州绿地设厂，新建新能源制造工厂。",
        "A greenfield new-energy manufacturing plant in the State of São Paulo, Brazil.",
        "Implantação de nova planta industrial greenfield de energia renovável no Estado de São Paulo, Brasil.",
    ],
)
def test_material_match_accepts_explicit_four_dimension_evidence_across_languages(
    material_text: str,
) -> None:
    registry = CapabilityPackRegistry(app_env="production")

    match = registry.match_material(material_text=material_text)

    assert match.pack_id == FORMAL_PACK_ID


@pytest.mark.parametrize(
    "material_text",
    [
        "材料标签写作巴西圣保罗州新能源 greenfield，但项目实际选址为 Rio de Janeiro。",
        "A greenfield new-energy project in São Paulo, Brazil will acquire an existing factory.",
        "Projeto greenfield de energia renovável em São Paulo, Brasil para expansão de fábrica existente.",
    ],
)
def test_material_match_rejects_out_of_scope_state_or_brownfield_actions(
    material_text: str,
) -> None:
    registry = CapabilityPackRegistry(app_env="production")

    with pytest.raises(CapabilityPackUnsupportedError):
        registry.match_material(
            material_text=material_text,
            country_hint="BR",
            state_hint="sao_paulo",
            industry_hint="new_energy_manufacturing",
            action_type_hint="greenfield_plant",
        )


def test_explicit_rio_state_hint_cannot_be_silently_rewritten_to_sao_paulo() -> None:
    registry = CapabilityPackRegistry(app_env="production")

    with pytest.raises(CapabilityPackUnsupportedError):
        registry.match_material(
            material_text="巴西圣保罗州新能源制造绿地设厂项目。",
            state_hint="RJ",
        )


def test_loader_hashes_and_parses_each_artifact_from_one_read(monkeypatch: pytest.MonkeyPatch) -> None:
    original_read_bytes = Path.read_bytes
    counts = {"brazil_new_energy.json": 0, "brazil_legal_corpus.json": 0}

    def counted_read_bytes(path: Path) -> bytes:
        if path.name in counts:
            counts[path.name] += 1
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    CapabilityPackRegistry(app_env="production").get(FORMAL_PACK_ID)

    assert counts == {"brazil_new_energy.json": 1, "brazil_legal_corpus.json": 1}
