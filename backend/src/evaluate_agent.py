"""Evaluación offline del modelo NEXTCART contra sus baselines, en el equipo local.

Split: oficial Instacart. Historial = órdenes `prior` de cada usuario; objetivo =
su orden `train` (la más reciente, verificado anti-leakage en la auditoría S5).
Los usuarios `test` no tienen ground truth público y se excluyen.

Ejemplo:
    python src/evaluate_agent.py --data-dir dataset \
        --model ../artifacts/nextcart_model.json --output ../reports/model_metrics.json
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from src.artifacts import ModelLoadError, load_model_json, verify_manifest
from src.config import (
    DATASET_FILES,
    DEFAULTS,
    PROJECT_ROOT,
    dataset_file,
    resolve_data_dir,
)
from src.storage import StepTimer, ensure_dir, log_step, now_utc_iso, write_json_atomic

MODEL_VARIANTS = ("topfreq", "cooccur", "nextcart_final")
VARIANT_DESCRIPTIONS = {
    "topfreq": "Baseline: productos globalmente más frecuentes (popularidad pura).",
    "cooccur": "Coocurrencia por confianza, sin blend de popularidad, boost de "
    "recompra ni filtros avanzados.",
    "nextcart_final": "Modelo final: coocurrencia + popularidad + boost de recompra "
    "sobre historial; filtros de inventario/rechazo aplicados "
    "(inercios offline: Instacart no expone stock ni rechazos).",
}

_G: dict[str, Any] = {}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluación offline (Precision/Recall/HitRate/MAP @K, cobertura, "
        "repeat/explore, latencia) del artefacto NEXTCART.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument(
        "--model",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "nextcart_model.json",
        help="Artefacto de modelo a evaluar.",
    )
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument(
        "--no-verify", action="store_true", help="Omite la verificación del manifiesto."
    )
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "reports" / "model_metrics.json"
    )
    parser.add_argument(
        "--figures-dir", type=Path, default=PROJECT_ROOT / "reports" / "figures"
    )
    parser.add_argument("--seed", type=int, default=DEFAULTS.seed)
    parser.add_argument(
        "--max-eval-users",
        type=int,
        default=None,
        help="Submuestreo opcional de usuarios evaluados "
        "(queda documentado; por defecto se evalúan todos).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULTS.workers,
        help="Procesos paralelos de evaluación (1 = en proceso).",
    )
    parser.add_argument(
        "--eval-ks",
        type=str,
        default="1,3,5,10",
        help="Valores de K separados por coma.",
    )
    parser.add_argument("--duckdb-memory-limit", default=DEFAULTS.duckdb_memory_limit)
    parser.add_argument(
        "--spill-dir", type=Path, default=Path(DEFAULTS.duckdb_spill_dir)
    )
    return parser.parse_args(argv)


def connect(args: argparse.Namespace) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    con.execute(f"SET memory_limit='{args.duckdb_memory_limit}'")
    ensure_dir(args.spill_dir)
    con.execute(f"SET temp_directory='{args.spill_dir}'")
    con.execute("SET preserve_insertion_order=false")
    return con


def require_files(data_dir: Path) -> dict[str, Path]:
    paths = {key: dataset_file(data_dir, key) for key in DATASET_FILES}
    needed = ["orders", "order_products_prior", "order_products_train"]
    missing = [k for k in needed if not paths[k].is_file()]
    if missing:
        sys.exit(
            "ERROR: faltan archivos del dataset para evaluar: "
            + ", ".join(str(paths[k]) for k in missing)
            + f"\nColoca los CSV del dataset Instacart en '{data_dir}' y reejecuta."
        )
    return paths


def load_eval_data(
    con: duckdb.DuckDBPyConnection,
    paths: dict[str, Path],
    seed: int,
    max_eval_users: int | None,
) -> tuple[dict[int, list[int]], dict[int, set[int]], dict[str, Any]]:
    con.execute(f"""
        CREATE OR REPLACE VIEW orders_v AS
        SELECT order_id, user_id, eval_set, order_number
        FROM read_csv_auto('{paths["orders"]}', header=true)
    """)
    users_df = con.execute(
        "SELECT DISTINCT user_id FROM orders_v WHERE eval_set='train' ORDER BY user_id"
    ).pl()
    user_ids = users_df["user_id"].to_list()
    sampling = {"used": False, "method": None, "seed": seed, "description": None}
    con.execute(
        "CREATE OR REPLACE TEMP TABLE eval_users AS "
        "SELECT DISTINCT user_id FROM orders_v WHERE eval_set='train'"
    )
    if max_eval_users is not None and max_eval_users < len(user_ids):
        rng = np.random.default_rng(seed)
        chosen = rng.choice(user_ids, size=max_eval_users, replace=False)
        user_ids = sorted(int(u) for u in chosen)
        con.execute(
            "CREATE OR REPLACE TEMP TABLE eval_users AS SELECT unnest(?)::BIGINT AS user_id",
            [user_ids],
        )
        sampling = {
            "used": True,
            "method": "muestreo aleatorio de usuarios eval_set=train (sin reemplazo)",
            "seed": seed,
            "description": f"{len(user_ids)} de {len(users_df)} usuarios train evaluados; "
            "las métricas no representan al dataset completo.",
        }
    user_filter = "WHERE o.user_id IN (SELECT user_id FROM eval_users)"

    hist_df = con.execute(f"""
        SELECT o.user_id, p.product_id, o.order_number, p.add_to_cart_order
        FROM read_csv_auto('{paths["order_products_prior"]}', header=true) p
        JOIN orders_v o USING(order_id)
        {user_filter}
        ORDER BY o.user_id, o.order_number, p.add_to_cart_order
    """).pl()
    tgt_df = con.execute(f"""
        SELECT o.user_id, p.product_id
        FROM read_csv_auto('{paths["order_products_train"]}', header=true) p
        JOIN orders_v o USING(order_id)
        {user_filter}
        ORDER BY o.user_id, p.add_to_cart_order
    """).pl()

    grouped = hist_df.group_by("user_id", maintain_order=True).agg(pl.col("product_id"))
    histories = {
        int(u): items
        for u, items in zip(
            grouped["user_id"].to_list(), grouped["product_id"].to_list()
        )
    }
    tgrouped = tgt_df.group_by("user_id", maintain_order=True).agg(pl.col("product_id"))
    targets = {
        int(u): set(items)
        for u, items in zip(
            tgrouped["user_id"].to_list(), tgrouped["product_id"].to_list()
        )
    }
    keep = [u for u in histories if u in targets]
    histories = {u: histories[u] for u in keep}
    targets = {u: targets[u] for u in keep}
    stats = {
        "users_in_split_train": int(len(user_ids)),
        "users_evaluated": len(keep),
        "baskets_evaluated": len(keep),
        "history_rows": hist_df.height,
        "target_rows": tgt_df.height,
    }
    return histories, targets, {**sampling, **{"_stats": stats}}


def _init_worker(
    model: dict[str, Any],
    histories: dict[int, list[int]],
    targets: dict[int, set[int]],
    ks: list[int],
) -> None:
    params = model.get("parameters", {})
    _G["rules"] = {
        int(k): [(int(r[0]), int(r[1]), float(r[2]), float(r[3])) for r in v]
        for k, v in model.get("association_rules", {}).items()
    }
    _G["popular_ids"] = [p["product_id"] for p in model.get("popular_products", [])]
    _G["pop_norm"] = {
        p["product_id"]: float(p["score"]) for p in model.get("popular_products", [])
    }
    _G["pop_weight"] = float(params.get("pop_weight", 0.15))
    _G["repeat_boost"] = float(params.get("repeat_boost", 0.25))
    _G["history_items_used"] = int(params.get("history_items_used", 50))
    _G["lift_cap"] = float(params.get("lift_cap", 5.0))
    _G["histories"] = histories
    _G["targets"] = targets
    _G["ks"] = ks
    _G["max_k"] = max(ks)


def score_candidates(
    context: list[tuple[int, float]], variant: str
) -> dict[int, float]:
    rules = _G["rules"]
    best: dict[int, float] = {}
    for pid, w in context:
        for cons, _count, conf, lift in rules.get(pid, ()):
            contribution = (
                w * conf * (0.5 + 0.5 * min(lift, _G["lift_cap"]) / _G["lift_cap"])
            )
            prev = best.get(cons)
            if prev is None or contribution > prev:
                best[cons] = contribution
    if variant == "cooccur":
        return best
    pop_w = _G["pop_weight"]
    boost = _G["repeat_boost"]
    pop_norm = _G["pop_norm"]
    return {pid: base + pop_w * pop_norm.get(pid, 0.0) for pid, base in best.items()}


def evaluate_user(user_id: int, variant: str) -> dict[str, Any]:
    history = _G["histories"][user_id]
    target = _G["targets"][user_id]
    t0 = time.perf_counter()
    if variant == "topfreq":
        ranked = _G["popular_ids"][: _G["max_k"]]
    else:
        context = [(pid, 1.0) for pid in history[-_G["history_items_used"] :]]
        scored = score_candidates(context, variant)
        if variant == "nextcart_final":
            pop_norm = _G["pop_norm"]
            boost = _G["repeat_boost"]
            hist_set = set(history)
            scored = {
                pid: s + (boost * pop_norm.get(pid, 0.0) if pid in hist_set else 0.0)
                for pid, s in scored.items()
            }
        ranked = sorted(scored, key=lambda p: (-scored[p], p))[: _G["max_k"]]
    latency_ms = (time.perf_counter() - t0) * 1000.0

    out: dict[str, Any] = {
        "latency_ms": latency_ms,
        "n_target": len(target),
        "hits_at": {},
        "aps": {},
        "recommended": ranked,
        "hit_pids": set(),
    }
    for k in _G["ks"]:
        top = ranked[:k]
        hits = [p for p in top if p in target]
        out["hits_at"][k] = len(hits)
        out["hit_pids"].update(hits)
        out["aps"][k] = (
            (
                sum(
                    (sum(1 for q in top[: r + 1] if q in target) / (r + 1))
                    for r in range(len(top))
                    if top[r] in target
                )
                / min(len(target), k)
            )
            if target and hits
            else 0.0
        )
    return out


def _empty_agg(ks: list[int]) -> dict[str, Any]:
    return {
        "n_users": 0,
        "hits": {k: 0 for k in ks},
        "precision_sum": {k: 0.0 for k in ks},
        "recall_sum": {k: 0.0 for k in ks},
        "hit_users": {k: 0 for k in ks},
        "ap_sum": {k: 0.0 for k in ks},
        "latencies": [],
        "recommended_ids": set(),
        "repeat_hits": 0,
        "explore_hits": 0,
        "target_sizes": [],
    }


def _accumulate(
    agg: dict[str, Any], res: dict[str, Any], history_set: set[int], ks: list[int]
) -> None:
    agg["n_users"] += 1
    agg["latencies"].append(res["latency_ms"])
    agg["recommended_ids"].update(res["recommended"])
    agg["target_sizes"].append(res["n_target"])
    for pid in res["hit_pids"]:
        if pid in history_set:
            agg["repeat_hits"] += 1
        else:
            agg["explore_hits"] += 1
    for k in ks:
        agg["hits"][k] += res["hits_at"][k]
        agg["precision_sum"][k] += res["hits_at"][k] / k
        agg["recall_sum"][k] += (
            res["hits_at"][k] / res["n_target"] if res["n_target"] else 0.0
        )
        agg["hit_users"][k] += 1 if res["hits_at"][k] > 0 else 0
        agg["ap_sum"][k] += res["aps"][k]


def _eval_chunk(user_ids: list[int], variant: str, ks: list[int]) -> dict[str, Any]:
    agg = _empty_agg(ks)
    for uid in user_ids:
        res = evaluate_user(uid, variant)
        _accumulate(agg, res, set(_G["histories"][uid]), ks)
    return agg


def run_variant(
    model: dict[str, Any],
    histories: dict[int, list[int]],
    targets: dict[int, set[int]],
    variant: str,
    ks: list[int],
    workers: int,
) -> dict[str, Any]:
    user_ids = sorted(histories)
    agg = _empty_agg(ks)
    if workers <= 1:
        _init_worker(model, histories, targets, ks)
        for uid in user_ids:
            res = evaluate_user(uid, variant)
            _accumulate(agg, res, set(histories[uid]), ks)
    else:
        chunk = max(1, len(user_ids) // (workers * 8))
        chunks = [user_ids[i : i + chunk] for i in range(0, len(user_ids), chunk)]
        ctx = mp.get_context("fork")
        with ctx.Pool(
            processes=workers,
            initializer=_init_worker,
            initargs=(model, histories, targets, ks),
        ) as pool:
            for part in pool.starmap(_eval_chunk, [(c, variant, ks) for c in chunks]):
                for key in ("n_users", "repeat_hits", "explore_hits"):
                    agg[key] += part[key]
                for k in ks:
                    agg["hits"][k] += part["hits"][k]
                    agg["precision_sum"][k] += part["precision_sum"][k]
                    agg["recall_sum"][k] += part["recall_sum"][k]
                    agg["hit_users"][k] += part["hit_users"][k]
                    agg["ap_sum"][k] += part["ap_sum"][k]
                agg["latencies"].extend(part["latencies"])
                agg["recommended_ids"].update(part["recommended_ids"])
                agg["target_sizes"].extend(part["target_sizes"])
    return finalize_agg(agg, ks)


def _eval_chunk_star(args: tuple[list[int], str, list[int]]) -> dict[str, Any]:
    return _eval_chunk(*args)


def finalize_agg(agg: dict[str, Any], ks: list[int]) -> dict[str, Any]:
    n = agg["n_users"] or 1
    total_hits = agg["repeat_hits"] + agg["explore_hits"]
    lat = sorted(agg["latencies"]) or [0.0]
    metrics_by_k: dict[str, Any] = {}
    for k in ks:
        metrics_by_k[str(k)] = {
            "precision_at_k": agg["precision_sum"][k] / n,
            "recall_at_k": agg["recall_sum"][k] / n,
            "hit_rate_at_k": agg["hit_users"][k] / n,
            "map_at_k": agg["ap_sum"][k] / n,
        }
    p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))]
    return {
        "n_users": agg["n_users"],
        "metrics_by_k": metrics_by_k,
        "catalog_coverage": {
            "distinct_recommended": len(agg["recommended_ids"]),
        },
        "repeat_explore": {
            "repeat_hits": agg["repeat_hits"],
            "explore_hits": agg["explore_hits"],
            "repeat_share_of_hits": (agg["repeat_hits"] / total_hits)
            if total_hits
            else None,
        },
        "latency_ms": {
            "mean": float(np.mean(lat)),
            "p95": float(p95),
            "max": float(lat[-1]),
        },
        "_recommended_ids": agg["recommended_ids"],
    }


def plot_metrics(
    results: dict[str, Any], ks: list[int], figures_dir: Path
) -> list[str]:
    ensure_dir(figures_dir)
    written: list[str] = []
    colors = {"topfreq": "#C44E52", "cooccur": "#DD8452", "nextcart_final": "#4C72B0"}
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    panels = [
        ("precision_at_k", "Precision@K"),
        ("recall_at_k", "Recall@K"),
        ("hit_rate_at_k", "HitRate@K"),
        ("map_at_k", "MAP@K"),
    ]
    for ax, (metric, title) in zip(axes.flat, panels):
        for variant in MODEL_VARIANTS:
            ys = [results[variant]["metrics_by_k"][str(k)][metric] for k in ks]
            ax.plot(ks, ys, marker="o", label=variant, color=colors[variant])
        ax.set_title(title)
        ax.set_xlabel("K")
        ax.set_xticks(ks)
        ax.grid(alpha=0.3)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Evaluación offline NEXTCART (split oficial prior→train)")
    fig.tight_layout()
    out = figures_dir / "model_metrics_at_k.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    written.append(out.name)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    names = list(MODEL_VARIANTS)
    cov = [results[v]["catalog_coverage"]["distinct_recommended"] for v in names]
    axes[0].bar(names, cov, color=[colors[v] for v in names])
    axes[0].set_title("Productos distintos recomendados")
    axes[0].tick_params(axis="x", rotation=15)
    rep = [results[v]["repeat_explore"]["repeat_share_of_hits"] or 0.0 for v in names]
    exp = [1 - r for r in rep]
    axes[1].bar(names, rep, color="#55A868", label="repeat")
    axes[1].bar(names, exp, bottom=rep, color="#8172B3", label="explore")
    axes[1].set_title("Composición de los aciertos (repeat vs explore)")
    axes[1].set_ylim(0, 1)
    axes[1].legend()
    axes[1].tick_params(axis="x", rotation=15)
    fig.tight_layout()
    out2 = figures_dir / "repeat_explore_share.png"
    fig.savefig(out2, dpi=140, bbox_inches="tight")
    plt.close(fig)
    written.append(out2.name)
    return written


def run_evaluation(
    model_path: Path, data_dir: Path, output: Path, args: argparse.Namespace
) -> dict[str, Any]:
    t_total = time.perf_counter()
    with StepTimer("Carga del artefacto de modelo (sin reentrenar)"):
        try:
            model = load_model_json(model_path)
            if not args.no_verify:
                verify_manifest(model_path, args.manifest)
        except ModelLoadError as exc:
            sys.exit(f"ERROR: {exc}")
        log_step(f"Modelo {model['model_version']} (estado={model.get('status')})")

    paths = require_files(Path(data_dir))
    con = connect(args)
    with StepTimer("Carga de historiales prior y cestas objetivo train"):
        histories, targets, sampling_meta = load_eval_data(
            con, paths, args.seed, args.max_eval_users
        )
        con.close()
    stats = sampling_meta.pop("_stats")
    log_step(f"Usuarios evaluados: {stats['users_evaluated']:,}")

    ks = [int(x) for x in args.eval_ks.split(",") if x.strip()]
    results: dict[str, Any] = {}
    for variant in MODEL_VARIANTS:
        with StepTimer(f"Evaluación del modelo: {variant}"):
            agg = run_variant(model, histories, targets, variant, ks, args.workers)
            results[variant] = agg
            log_step(
                f"{variant}: HitRate@{max(ks)}="
                f"{agg['metrics_by_k'][str(max(ks))]['hit_rate_at_k']:.4f}, "
                f"latencia media={agg['latency_ms']['mean']:.2f} ms"
            )

    figures_dir = Path(args.figures_dir)
    with StepTimer("Figuras de métricas"):
        fig_names = plot_metrics(results, ks, figures_dir)
    for variant in MODEL_VARIANTS:
        results[variant]["catalog_coverage"]["catalog_size"] = (
            len(model.get("catalog_metadata", {}).get("products", {})) or None
        )
        cat = results[variant]["catalog_coverage"]
        if cat.get("catalog_size"):
            cat["coverage_fraction"] = cat["distinct_recommended"] / cat["catalog_size"]
        else:
            cat["coverage_fraction"] = None
        results[variant].pop("_recommended_ids", None)

    payload = {
        "metadata": {
            "generated_at_utc": now_utc_iso(),
            "python_version": sys.version.split()[0],
            "seed": args.seed,
            "data_path": str(data_dir),
            "model_path": str(model_path),
            "model_version": model["model_version"],
            "model_status": model.get("status"),
            "sampling": sampling_meta,
            "workers": args.workers,
            "wall_seconds": round(time.perf_counter() - t_total, 1),
        },
        "methodology": {
            "split": "oficial Instacart prior/train (usuarios con eval_set='train')",
            "description": (
                "Historial = todas las órdenes prior del usuario; objetivo = su orden "
                "train (la más reciente). Las reglas del modelo se entrenaron solo con "
                "prior. Los usuarios eval_set='test' se excluyen por no tener ground "
                "truth público. Offline no hay carrito parcial, inventario real ni "
                "rechazos: los filtros del modelo final son inercios aquí y solo se "
                "prueban en inferencia/tests."
            ),
            **stats,
            "eval_ks": ks,
            "history_items_used": model.get("parameters", {}).get("history_items_used"),
        },
        "models": {
            variant: {"description": VARIANT_DESCRIPTIONS[variant], **results[variant]}
            for variant in MODEL_VARIANTS
        },
        "figures": [f"figures/{name}" for name in fig_names],
        "warnings": [
            "Recall@K/Precision@K/HitRate@K/MAP@K son métricas offline de predicción "
            "de cesta; NO son tasas de conversión ni de aceptación comercial.",
            "Instacart no contiene impresiones de recomendaciones, exposición, grupo "
            "control ni aceptación: el objetivo comercial de 12% de aceptación solo "
            "puede medirse con un A/B real de dos semanas en producción.",
            "Los filtros de inventario y rechazo del modelo final no se pueden "
            "ejecutar offline con datos reales de la tienda.",
            "Cobertura y latencia dependen del hardware local y del tamaño del modelo.",
        ],
    }
    write_json_atomic(output, payload)
    log_step(f"Métricas guardadas en {Path(output).resolve()}")
    return payload


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_dir = resolve_data_dir(args.data_dir)
    log_step(f"Directorio de datos: {data_dir}")
    run_evaluation(args.model, data_dir, args.output, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
