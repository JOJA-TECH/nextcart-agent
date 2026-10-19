"""Tests de contrato del backend FastAPI (sin dataset real, fixtures pequeñas)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.backend import create_app


@pytest.fixture()
def client_with_model(tiny_model_path: Path, tmp_path: Path):
    app = create_app(model_path=str(tiny_model_path),
                     events_path=tmp_path / "events.jsonl",
                     admin_token="tok-secreto",
                     catalog_db_path=tmp_path / "catalog.db",
                     catalog_data_dir=tmp_path / "sin-dataset")
    with TestClient(app) as c:
        yield c, tmp_path


@pytest.fixture()
def client_without_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NEXTCART_MODEL_PATH", raising=False)
    app = create_app(model_path=None, events_path=tmp_path / "events.jsonl",
                     catalog_db_path=tmp_path / "catalog.db",
                     catalog_data_dir=tmp_path / "sin-dataset")
    with TestClient(app) as c:
        yield c


def test_health_with_model(client_with_model):
    client, _ = client_with_model
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "model_loaded": True,
                    "model_version": "test-0.0.1", "error": None,
                    "catalog_loaded": False}


def test_health_without_model_reports_false(client_without_model):
    r = client_without_model.get("/health")
    body = r.json()
    assert body["status"] == "degraded"
    assert body["model_loaded"] is False
    assert body["error"]


def test_recommendations_503_without_model(client_without_model):
    r = client_without_model.post("/v1/recommendations",
                                  json={"session_id": "s", "cart": [1]})
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "model_not_loaded"


def test_recommendations_ok(client_with_model):
    client, _ = client_with_model
    payload = {
        "session_id": "sess-001",
        "cart": [1],
        "navigation": [{"type": "view", "product_id": 4}],
        "recent_history": [[1, 2]],
        "rejected": [3],
        "inventory": {"6": False},
        "k": 3,
    }
    r = client.post("/v1/recommendations", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "sess-001"
    assert body["fallback"] is False
    assert body["model_version"] == "test-0.0.1"
    assert 0 < body["latency_ms"] < 10_000
    ids = [item["product_id"] for item in body["recommendations"]]
    assert 1 not in ids and 3 not in ids and 6 not in ids
    for item in body["recommendations"]:
        assert set(item) >= {"product_id", "score", "reason", "source"}
        assert item["source"] in ("association_rule", "global_frequency")


def test_recommendations_validation_error(client_with_model):
    client, _ = client_with_model
    r = client.post("/v1/recommendations", json={"session_id": "s", "cart": [1], "k": 99})
    assert r.status_code == 422


def test_impression_and_feedback_flow(client_with_model):
    client, tmp = client_with_model
    r = client.post("/v1/recommendations", json={"session_id": "sess-001",
                                                 "cart": [1], "k": 2})
    assert r.status_code == 200
    r = client.post("/v1/events/impression", json={
        "session_id": "sess-001", "recommendation_ids": [2, 4],
        "cart": [1], "model_version": "test-0.0.1",
    })
    assert r.status_code == 202
    for event in ("accepted", "rejected", "ignored"):
        r = client.post("/v1/events/feedback", json={
            "session_id": "sess-001", "product_id": 2, "event": event,
            "recommendation_ids": [2, 4],
        })
        assert r.status_code == 202
    r = client.post("/v1/events/feedback", json={
        "session_id": "s", "product_id": 2, "event": "clicked"})
    assert r.status_code == 422

    summary = client.get("/v1/metrics/summary").json()
    assert summary["impressions"] == 1
    assert summary["accepted"] == 1
    assert summary["rejected"] == 1
    assert summary["ignored"] == 1
    assert summary["acceptance_rate_observed"] == 1.0
    assert summary["model_version"] == "test-0.0.1"
    assert "A/B" in summary["disclaimer"]
    assert summary["latency_mean_ms"] > 0
    assert 0 <= summary["catalog_coverage_observed"] <= 1

    lines = [json.loads(x) for x in
             (tmp / "events.jsonl").read_text().splitlines()]
    kinds = {line["type"] for line in lines}
    assert {"recommendation", "impression", "feedback"} <= kinds
    for line in lines:
        assert "recent_history" not in line


def test_admin_reload_requires_token(client_with_model):
    client, _ = client_with_model
    assert client.post("/v1/admin/reload-model").status_code == 403
    assert client.post("/v1/admin/reload-model",
                       headers={"x-admin-token": "mal"}).status_code == 403
    r = client.post("/v1/admin/reload-model",
                    headers={"x-admin-token": "tok-secreto"})
    assert r.status_code == 200
    assert r.json()["reloaded"] is True


def test_admin_reload_disabled_without_token_config(tmp_path: Path,
                                                    tiny_model_path: Path):
    app = create_app(model_path=str(tiny_model_path),
                     events_path=tmp_path / "events.jsonl", admin_token=None)
    with TestClient(app) as c:
        r = c.post("/v1/admin/reload-model")
        assert r.status_code == 404


def test_vercel_uses_writable_directory_for_event_log(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("NEXTCART_EVENTS_PATH", raising=False)

    app = create_app()

    assert app.state.nc.events_path == (
        Path(tempfile.gettempdir()) / "nextcart-agent" / "events.jsonl"
    )
