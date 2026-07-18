from __future__ import annotations

from types import SimpleNamespace

from app.core import database


def test_postgres_initialization_never_calls_create_all(monkeypatch, tmp_path) -> None:
    fake_engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    create_all_calls: list[object] = []
    monkeypatch.setattr(database, "engine", fake_engine)
    monkeypatch.setattr(database, "settings", SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setattr(
        database.Base.metadata,
        "create_all",
        lambda *, bind: create_all_calls.append(bind),
    )

    database.init_db()

    assert create_all_calls == []
