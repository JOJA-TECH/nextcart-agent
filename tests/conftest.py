"""Configuración común de tests: ruta del proyecto y fixtures pequeñas."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.storage import sha256_of_file, write_json_atomic  # noqa: E402

MINI_DATASET = ROOT / "tests" / "fixtures" / "mini_dataset"


def build_tiny_model() -> dict:
    """Modelo mínimo pero representativo para inferencia/backend."""
    return {
        "model_version": "test-0.0.1",
        "trained_at_utc": "2026-01-01T00:00:00Z",
        "algorithm": "cooccurrence_frequency",
        "format_version": 1,
        "status": "experimental",
        "parameters": {
            "min_support": 2,
            "top_k_rules": 10,
            "history_items_used": 50,
            "pop_weight": 0.15,
            "repeat_boost": 0.25,
            "nav_weight": 0.5,
            "rejection_penalty": 0.2,
            "lift_cap": 5.0,
            "rule_fields": ["consequent_id", "count", "confidence", "lift"],
        },
        "training_statistics": {"n_rules": 4},
        "popular_products": [
            {"product_id": 5, "count": 20, "recency_mean": 0.9, "score": 1.0},
            {"product_id": 6, "count": 15, "recency_mean": 0.8, "score": 0.8},
            {"product_id": 3, "count": 10, "recency_mean": 0.7, "score": 0.6},
            {"product_id": 4, "count": 8, "recency_mean": 0.6, "score": 0.4},
        ],
        "association_rules": {
            "1": [[2, 10, 0.9, 3.0], [3, 5, 0.5, 2.0]],
            "2": [[1, 10, 0.8, 2.5], [4, 3, 0.3, 1.5]],
        },
        "catalog_metadata": {
            "products": {
                "1": {"aisle_id": 1, "department_id": 1, "product_name": "P1"},
                "2": {"aisle_id": 1, "department_id": 1, "product_name": "P2"},
                "3": {"aisle_id": 2, "department_id": 1, "product_name": "P3"},
                "4": {"aisle_id": 3, "department_id": 1, "product_name": "P4"},
                "5": {"aisle_id": 2, "department_id": 1, "product_name": "P5"},
                "6": {"aisle_id": 2, "department_id": 1, "product_name": "P6"},
            },
            "aisles": {"1": "fruit", "2": "dairy", "3": "bakery"},
            "departments": {"1": "produce"},
        },
    }


@pytest.fixture()
def tiny_model() -> dict:
    return build_tiny_model()


@pytest.fixture()
def tiny_model_path(tmp_path: Path, tiny_model: dict) -> Path:
    path = tmp_path / "nextcart_model.json"
    write_json_atomic(path, tiny_model, indent=None)
    manifest = {
        "model_path": path.name,
        "model_version": tiny_model["model_version"],
        "created_at_utc": "2026-01-01T00:00:00Z",
        "source_dataset": "fixture",
        "training_code_version": "test",
        "audit_results_path": None,
        "metrics_path": None,
        "sha256": sha256_of_file(path),
    }
    write_json_atomic(tmp_path / "artifact_manifest.json", manifest)
    return path


@pytest.fixture()
def mini_dataset_dir() -> Path:
    assert MINI_DATASET.is_dir(), f"Fixture ausente: {MINI_DATASET}"
    return MINI_DATASET
