from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import create_app
from app.models import (  # noqa: F401
    audit_log,
    delivery_assurance,
    legal_source_version,
    mechanism,
    scenario,
    user,
)
from scripts.seed_competition_demo import seed_competition_demo


@pytest.fixture()
def competition_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database_path = tmp_path / "vela_competition.db"
    material_path = tmp_path / "competition_materials"
    monkeypatch.setenv("VELA_APP_MODE", "competition")
    monkeypatch.setenv("VELA_COMPETITION_DB_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("VELA_SCENARIO_MATERIALS_DIR", str(material_path))
    get_settings.cache_clear()

    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        scenario_id = seed_competition_demo(db)

    app = create_app()

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        yield client, scenario_id, material_path
    finally:
        client.close()
        get_settings.cache_clear()


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Demo1234!"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_business_center_returns_only_business_safe_content(competition_api) -> None:
    client, scenario_id, _material_path = competition_api
    business_headers = _login(client, "biz@demo.vela")
    legal_headers = _login(client, "legal@demo.vela")

    response = client.get(
        f"/api/v1/competition/scenarios/{scenario_id}/business-center",
        headers=business_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_name"] == "Aurora 储能系统集成工厂"
    assert [item["title"] for item in body["supplements"]] == [
        "最终场址或选址状态",
        "危险品最大库存",
        "主要生产设备及活动分类",
    ]
    assert body["current_status"] == "待业务补充"
    serialized = json.dumps(body, ensure_ascii=False)
    for forbidden in (
        "ResearchItem",
        "Claim",
        "CoverageProof",
        "reason_code",
        "MISSING_FACT",
        "UNANSWERABLE",
        "blocked_external",
    ):
        assert forbidden not in serialized

    assert client.get(
        f"/api/v1/competition/scenarios/{scenario_id}/business-center",
        headers=legal_headers,
    ).status_code == 403


def test_business_upload_confirm_and_submit_flow(competition_api) -> None:
    client, scenario_id, material_path = competition_api
    headers = _login(client, "biz@demo.vela")
    center = client.get(
        f"/api/v1/competition/scenarios/{scenario_id}/business-center",
        headers=headers,
    ).json()

    upload = client.post(
        f"/api/v1/competition/scenarios/{scenario_id}/business-center/materials",
        headers=headers,
        data={"purpose": "supplement"},
        files={"file": ("aurora_supplement.txt", b"site status: selecting", "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    assert any(
        item["filename"] == "aurora_supplement.txt"
        for item in upload.json()["materials"]
    )
    assert len(list(material_path.rglob("aurora_supplement.txt"))) == 0
    assert len(list(material_path.rglob("*__aurora_supplement.txt"))) == 1

    fact = center["facts"][0]
    confirmation = client.post(
        f"/api/v1/competition/scenarios/{scenario_id}/business-center/facts/{fact['id']}/confirm",
        headers=headers,
        json={"value": fact["value"]},
    )
    assert confirmation.status_code == 200, confirmation.text
    assert confirmation.json()["facts"][0]["status"] == "已确认"

    submit = client.post(
        f"/api/v1/competition/scenarios/{scenario_id}/business-center/submit",
        headers=headers,
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["current_status"] == "已补充，等待法务复核"
    assert all(item["status"] == "已补充，法务复核中" for item in submit.json()["supplements"])


def test_business_is_forbidden_from_every_legal_competition_api(competition_api) -> None:
    client, scenario_id, _material_path = competition_api
    business_headers = _login(client, "biz@demo.vela")
    legal_headers = _login(client, "legal@demo.vela")
    legal_only_paths = [
        f"/api/v1/scenarios/{scenario_id}",
        f"/api/v1/scenarios/{scenario_id}/mechanism/audit",
        f"/api/v1/scenarios/{scenario_id}/mechanism/coverage-tasks",
        f"/api/v1/scenarios/{scenario_id}/mechanism/claims/latest",
        f"/api/v1/scenarios/{scenario_id}/mechanism/research-items/latest",
        f"/api/v1/scenarios/{scenario_id}/mechanism/coverage-proofs/latest",
        f"/api/v1/scenarios/{scenario_id}/delivery-assurance/status",
    ]
    for path in legal_only_paths:
        response = client.get(path, headers=business_headers)
        assert response.status_code == 403, (path, response.text)
        assert client.get(path, headers=legal_headers).status_code == 200, path

    assert client.get(
        f"/api/v1/scenarios/{scenario_id}/mechanism/material-ledger",
        headers=business_headers,
    ).status_code == 200
    assert client.get(
        f"/api/v1/scenarios/{scenario_id}/mechanism/facts",
        headers=business_headers,
    ).status_code == 200


def test_development_mode_keeps_owner_scenario_access(
    competition_api,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, scenario_id, _material_path = competition_api
    headers = _login(client, "biz@demo.vela")
    monkeypatch.setenv("VELA_APP_MODE", "development")
    get_settings.cache_clear()

    response = client.get(f"/api/v1/scenarios/{scenario_id}", headers=headers)
    assert response.status_code == 200, response.text


def test_competition_start_keeps_one_frontend_port_and_isolated_materials() -> None:
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "start_competition.sh"
    ).read_text(encoding="utf-8")
    assert 'FRONTEND_URL="http://127.0.0.1:5180"' in script
    assert 'VITE_APP_MODE="competition"' in script
    assert 'VITE_COMPETITION_SCENARIO_ID="$AURORA_SCENARIO_ID"' in script
    assert 'VELA_SCENARIO_MATERIALS_DIR="$COMPETITION_MATERIALS"' in script
    assert "--port 5180" in script
    assert "--port 5181" not in script
