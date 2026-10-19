"""Tests de inferencia con el artefacto pequeño (sin dataset real)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.artifacts import ModelLoadError, verify_manifest
from src.inference import NextCartRecommender
from src.storage import write_json_atomic


@pytest.fixture()
def rec(tiny_model_path: Path) -> NextCartRecommender:
    return NextCartRecommender.load(tiny_model_path)


def test_cooccurrence_rule_fires(rec: NextCartRecommender):
    out = rec.recommend({"session_id": "s1", "cart": [1], "k": 3})
    ids = [r["product_id"] for r in out["recommendations"]]
    assert 2 in ids, "la regla 1->2 (conf 0.9) debe aparecer"
    top = out["recommendations"][0]
    assert top["source"] == "association_rule"
    assert "coocurrencia" in top["reason"]
    assert out["fallback"] is False
    assert out["model_version"] == "test-0.0.1"


def test_cart_items_are_excluded(rec: NextCartRecommender):
    out = rec.recommend({"session_id": "s1", "cart": [1, 2], "k": 5})
    ids = {r["product_id"] for r in out["recommendations"]}
    assert 1 not in ids and 2 not in ids


def test_rejected_items_are_excluded(rec: NextCartRecommender):
    out = rec.recommend({"session_id": "s1", "cart": [1], "rejected": [2], "k": 5})
    ids = {r["product_id"] for r in out["recommendations"]}
    assert 2 not in ids


def test_out_of_stock_items_are_excluded(rec: NextCartRecommender):
    out = rec.recommend({"session_id": "s1", "cart": [1],
                         "inventory": {"2": False}, "k": 5})
    ids = {r["product_id"] for r in out["recommendations"]}
    assert 2 not in ids


def test_unknown_inventory_defaults_to_available(rec: NextCartRecommender):
    out = rec.recommend({"session_id": "s1", "cart": [1],
                         "inventory": {"99999": False}, "k": 3})
    ids = {r["product_id"] for r in out["recommendations"]}
    assert 2 in ids


def test_empty_cart_uses_popular_fallback(rec: NextCartRecommender):
    out = rec.recommend({"session_id": "s1", "cart": [], "k": 3})
    assert out["fallback"] is True
    assert [r["product_id"] for r in out["recommendations"]] == [5, 6, 3]
    assert all(r["source"] == "global_frequency" for r in out["recommendations"])
    assert any("vacío" in w for w in out["warnings"])


def test_user_without_history_cold_start(rec: NextCartRecommender):
    out = rec.recommend({"session_id": "s1", "cart": [1], "k": 3})
    assert out["fallback"] is False
    assert any("sin historial" in w for w in out["warnings"])


def test_no_candidates_fallback_to_popular(tmp_path: Path):
    model = {
        "model_version": "empty-1",
        "algorithm": "cooccurrence_frequency",
        "format_version": 1,
        "parameters": {"pop_weight": 0.15, "repeat_boost": 0.25, "lift_cap": 5.0},
        "popular_products": [
            {"product_id": 5, "count": 3, "recency_mean": 0.5, "score": 1.0},
            {"product_id": 6, "count": 2, "recency_mean": 0.4, "score": 0.5},
        ],
        "association_rules": {},
        "catalog_metadata": {"products": {"5": {}, "6": {}}, "aisles": {},
                             "departments": {}},
    }
    path = tmp_path / "m.json"
    write_json_atomic(path, model, indent=None)
    rec = NextCartRecommender.load(path, verify=False)
    out = rec.recommend({"session_id": "s", "cart": [999], "k": 3})
    assert out["fallback"] is True
    assert [r["product_id"] for r in out["recommendations"]] == [5, 6]
    assert any("sin candidatos" in w for w in out["warnings"])


def test_k_is_respected(rec: NextCartRecommender):
    out = rec.recommend({"session_id": "s", "cart": [1], "k": 2})
    assert len(out["recommendations"]) <= 2


def test_missing_model_raises_clear_error(tmp_path: Path):
    with pytest.raises(ModelLoadError) as exc:
        NextCartRecommender.load(tmp_path / "no_existe.json")
    assert "train_agent" in str(exc.value)


def test_manifest_hash_mismatch_is_detected(tiny_model_path: Path):
    text = tiny_model_path.read_text(encoding="utf-8").replace('"test-0.0.1"',
                                                               '"test-0.0.2')
    tiny_model_path.write_text(text, encoding="utf-8")
    with pytest.raises(ModelLoadError) as exc:
        verify_manifest(tiny_model_path)
    assert "Hash" in str(exc.value) or "Versión" in str(exc.value)


def test_navigation_reject_moves_product_to_rejected(rec: NextCartRecommender):
    out = rec.recommend({
        "session_id": "s", "cart": [1],
        "navigation": [{"type": "reject", "product_id": 2}], "k": 5,
    })
    ids = {r["product_id"] for r in out["recommendations"]}
    assert 2 not in ids
