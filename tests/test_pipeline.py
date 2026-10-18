"""Tests de integración del flujo completo sobre el fixture mini_dataset.

Cubren: auditoría → entrenamiento (regla de coocurrencia pequeña) →
evaluación → inferencia con el artefacto resultante. Todo con datos
sintéticos pequeños en tests/fixtures/; nunca descargan el dataset real.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.artifacts import verify_manifest
from src.audit_dataset import run_audit
from src.evaluate_agent import run_evaluation
from src.inference import NextCartRecommender
from src.train_agent import parse_args as train_args
from src.train_agent import run_training


def test_audit_on_mini_dataset(mini_dataset_dir: Path, tmp_path: Path):
    out = tmp_path / "reports"
    results = run_audit(mini_dataset_dir, out, seed=42, pair_sample_users=1000)
    assert (out / "audit_results.json").is_file()
    assert (out / "dataset_audit.md").is_file()
    for key in ("S1_schema_integrity", "S2_sequential_history", "S3_basket_density",
                "S4_complementarity_signal", "S5_leakage_free_evaluation"):
        assump = results["assumptions"][key]
        assert assump["status"] in ("PASS", "WARN"), f"{key}: {assump['status']}"
        assert assump["interpretation"]
        assert isinstance(assump["limitations"], list)
    assert results["decision"]["dataset_usable"] is True
    figures = list((out / "figures").glob("*.png"))
    assert len(figures) >= 5
    md = (out / "dataset_audit.md").read_text(encoding="utf-8")
    assert "figures/" in md
    audit_json = json.loads((out / "audit_results.json").read_text(encoding="utf-8"))
    assert audit_json["metadata"]["dataset"] == \
        "instacart-online-grocery-basket-analysis-dataset"


def test_train_eval_infer_on_mini_dataset(mini_dataset_dir: Path, tmp_path: Path):
    model_path = tmp_path / "nextcart_model.json"
    metrics_path = tmp_path / "model_metrics.json"
    args = train_args([
        "--data-dir", str(mini_dataset_dir),
        "--output", str(model_path),
        "--metrics-output", str(metrics_path),
        "--min-support", "2",
        "--top-k", "10",
        "--max-antecedents", "50",
        "--top-popular", "5",
        "--block-size", "32",
    ])
    model = run_training(mini_dataset_dir, model_path, metrics_path, args=args)
    assert model["status"] == "candidate", model["training_statistics"]
    rules = model["association_rules"]
    assert "1" in rules
    consequents_1 = [r[0] for r in rules["1"]]
    assert 2 in consequents_1, "1 y 2 coaparecen en casi todas las cestas"
    top_rule = rules["1"][0]
    assert top_rule[0] == 2 and abs(top_rule[2] - 1.0) < 1e-6
    assert model_path.is_file() and (tmp_path / "artifact_manifest.json").is_file()
    verify_manifest(model_path)

    rec = NextCartRecommender.load(model_path)
    out = rec.recommend({"session_id": "mini", "cart": [1], "k": 2})
    assert out["recommendations"][0]["product_id"] == 2

    eval_args = [
        "--data-dir", str(mini_dataset_dir),
        "--model", str(model_path),
        "--output", str(metrics_path),
        "--figures-dir", str(tmp_path / "figures"),
        "--workers", "1",
        "--eval-ks", "1,3",
        "--no-verify",
    ]
    from src.evaluate_agent import parse_args as eval_parse
    payload = run_evaluation(model_path, mini_dataset_dir, metrics_path,
                             eval_parse(eval_args))
    assert metrics_path.is_file()
    for variant in ("topfreq", "cooccur", "nextcart_final"):
        m = payload["models"][variant]
        assert m["n_users"] == 8
        for k in ("1", "3"):
            for metric in ("precision_at_k", "recall_at_k", "hit_rate_at_k", "map_at_k"):
                assert 0.0 <= m["metrics_by_k"][k][metric] <= 1.0
    assert (tmp_path / "figures" / "model_metrics_at_k.png").is_file()
    assert any("A/B" in w for w in payload["warnings"])
