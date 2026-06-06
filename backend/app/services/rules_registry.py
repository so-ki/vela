from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"
INDEX_PATH = RULES_DIR / "index.json"

_index_cache: dict[str, Any] | None = None
_index_mtime: float | None = None
_rules_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class RulesPackNotFoundError(ValueError):
    pass


def load_index() -> dict[str, Any]:
    global _index_cache, _index_mtime
    mtime = INDEX_PATH.stat().st_mtime
    if _index_cache is None or _index_mtime != mtime:
        with open(INDEX_PATH, encoding="utf-8") as f:
            _index_cache = json.load(f)
        _index_mtime = mtime
    return _index_cache


def get_default_pack_id() -> str:
    return load_index().get("default_pack_id", "brazil_new_energy")


def get_pack_entry(pack_id: str) -> dict[str, Any] | None:
    for pack in load_index().get("packs", []):
        if pack.get("id") == pack_id:
            return pack
    return None


def resolve_pack_id(pack_id: str | None = None, country: str | None = None) -> str:
    if pack_id:
        if get_pack_entry(pack_id):
            return pack_id
        raise RulesPackNotFoundError(f"未知规则包：{pack_id}")

    if country:
        for region in load_index().get("regions", []):
            for entry in region.get("countries", []):
                if entry.get("id") == country and entry.get("default_pack_id"):
                    return entry["default_pack_id"]
        for pack in load_index().get("packs", []):
            if pack.get("primary_country") == country and pack.get("status", "active") == "active":
                return pack["id"]

    return get_default_pack_id()


def resolve_scenario_pack_id(
    *,
    rules_pack_id: str | None = None,
    country: str | None = None,
    checklist_payload: dict[str, Any] | None = None,
) -> str:
    if rules_pack_id:
        return resolve_pack_id(rules_pack_id)
    if checklist_payload:
        legacy = checklist_payload.get("industry_pack_id")
        if legacy and get_pack_entry(str(legacy)):
            return str(legacy)
    return resolve_pack_id(None, country)


def get_rules_file_path(pack_id: str | None = None) -> Path:
    resolved = resolve_pack_id(pack_id)
    entry = get_pack_entry(resolved)
    if not entry or not entry.get("file"):
        raise RulesPackNotFoundError(f"规则包未注册或缺少 file：{resolved}")
    path = RULES_DIR / entry["file"]
    if not path.exists():
        raise RulesPackNotFoundError(f"规则文件不存在：{path}")
    return path


def load_rules(pack_id: str | None = None) -> dict[str, Any]:
    resolved = resolve_pack_id(pack_id)
    path = get_rules_file_path(resolved)
    mtime = path.stat().st_mtime
    cached = _rules_cache.get(resolved)
    if cached and cached[0] == mtime:
        return cached[1]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _rules_cache[resolved] = (mtime, data)
    return data


def build_supported_locations(rules: dict[str, Any]) -> list[dict[str, str]]:
    jurisdiction = rules.get("jurisdiction", {})
    pack = rules.get("pack", {})
    country = pack.get("primary_country") or jurisdiction.get("id") or "brazil"
    locations: list[dict[str, str]] = []

    overlays = rules.get("state_overlays") or {}
    for state_id, state_def in overlays.items():
        state_name = state_def.get("name", state_id)
        cities = state_def.get("cities") or {}
        if cities:
            for city_id, city_def in cities.items():
                locations.append(
                    {
                        "country": country,
                        "state": state_id,
                        "state_name": state_name,
                        "city": city_id,
                        "city_name": city_def.get("name", city_id),
                    }
                )
        else:
            locations.append(
                {
                    "country": country,
                    "state": state_id,
                    "state_name": state_name,
                    "city": "",
                    "city_name": "",
                }
            )

    if not locations:
        default_state = jurisdiction.get("default_state")
        if default_state:
            locations.append(
                {
                    "country": country,
                    "state": default_state,
                    "state_name": default_state,
                    "city": "",
                    "city_name": "",
                }
            )
    return locations


def get_scene_defaults(pack_id: str | None = None) -> dict[str, str]:
    rules = load_rules(pack_id)
    pack = rules.get("pack", {})
    jurisdiction = rules.get("jurisdiction", {})
    locations = build_supported_locations(rules)
    loc = locations[0] if locations else {}
    industries = list(rules.get("industries", {}).keys())
    actions = list(rules.get("action_types", {}).keys())
    resolved = resolve_pack_id(pack_id)
    return {
        "rules_pack_id": pack.get("id") or resolved,
        "country": pack.get("primary_country") or jurisdiction.get("id") or "brazil",
        "state": loc.get("state") or jurisdiction.get("default_state") or "sao_paulo",
        "city": loc.get("city") or "campinas",
        "industry": industries[0] if industries else "new_energy",
        "action_type": actions[0] if actions else "greenfield_plant",
    }


def list_packs(*, include_planned: bool = False) -> list[dict[str, Any]]:
    index = load_index()
    out: list[dict[str, Any]] = []
    for entry in index.get("packs", []):
        status = entry.get("status", "active")
        if status != "active" and not include_planned:
            continue
        pack_id = entry["id"]
        summary = {
            "id": pack_id,
            "region": entry.get("region"),
            "primary_country": entry.get("primary_country"),
            "status": status,
        }
        try:
            rules = load_rules(pack_id)
            pack = rules.get("pack", {})
            summary.update(
                {
                    "name": pack.get("name", pack_id),
                    "version": pack.get("version"),
                    "focus": pack.get("focus"),
                    "industry_focus": pack.get("industry_focus"),
                }
            )
        except RulesPackNotFoundError:
            summary["name"] = pack_id
        out.append(summary)
    return out


def get_classification() -> dict[str, Any]:
    index = load_index()
    regions_out: list[dict[str, Any]] = []
    for region in index.get("regions", []):
        countries_out: list[dict[str, Any]] = []
        for country in region.get("countries", []):
            pack_id = country.get("default_pack_id")
            pack_summary: dict[str, Any] | None = None
            if pack_id:
                try:
                    pack_summary = next((p for p in list_packs() if p["id"] == pack_id), None)
                except RulesPackNotFoundError:
                    pack_summary = {"id": pack_id}
            countries_out.append(
                {
                    "id": country.get("id"),
                    "name": country.get("name"),
                    "name_pt": country.get("name_pt"),
                    "status": country.get("status", "active"),
                    "default_pack_id": pack_id,
                    "default_pack": pack_summary,
                }
            )
        regions_out.append(
            {
                "id": region.get("id"),
                "name": region.get("name"),
                "name_en": region.get("name_en"),
                "countries": countries_out,
            }
        )
    return {
        "schema_version": index.get("schema_version", "1.0"),
        "default_pack_id": get_default_pack_id(),
        "regions": regions_out,
        "packs": list_packs(include_planned=True),
    }
