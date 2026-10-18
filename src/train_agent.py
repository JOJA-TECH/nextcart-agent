"""Entrenamiento local del agente NEXTCART (baseline explicable, reproducible).

Construye un modelo de frecuencia + coocurrencia dentro de cestas usando
únicamente las órdenes `prior` del dataset Instacart local. No usa LLM.
El resultado es un artefacto JSON auditable más su manifiesto con hash SHA-256.

Ejemplo:
    python src/train_agent.py --data-dir dataset \
        --output artifacts/nextcart_model.json \
        --metrics-output reports/model_metrics.json --seed 42 --min-support 5 --top-k 100
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb
import numpy as np
import polars as pl

from src.artifacts import write_manifest
from src.config import (
    DATASET_FILES,
    DEFAULTS,
    MODEL_ALGORITHM,
    MODEL_FORMAT_VERSION,
    MODEL_STATUS_CANDIDATE,
    MODEL_STATUS_EXPERIMENTAL,
    PROJECT_ROOT,
    dataset_file,
    resolve_data_dir,
)
from src.storage import StepTimer, ensure_dir, log_step, now_utc_iso, write_json_atomic

RULE_FIELDS = ["consequent_id", "count", "confidence", "lift"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Entrena el modelo NEXTCART (coocurrencia + frecuencia) sobre "
        "las órdenes prior del dataset local.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directorio con los CSV del dataset.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "nextcart_model.json",
        help="Ruta del artefacto de modelo a generar.",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=None,
        help="Si se indica, aquí se guardan las estadísticas de entrenamiento (JSON).",
    )
    parser.add_argument("--seed", type=int, default=DEFAULTS.seed)
    parser.add_argument(
        "--min-support",
        type=int,
        default=DEFAULTS.min_support,
        help="Soporte mínimo (nº de cestas) para producto y par.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULTS.top_k_rules,
        help="Máximo de reglas por producto antecedente.",
    )
    parser.add_argument(
        "--max-antecedents",
        type=int,
        default=DEFAULTS.max_antecedents,
        help="Máximo de productos antecedentes (los más frecuentes).",
    )
    parser.add_argument(
        "--top-popular",
        type=int,
        default=DEFAULTS.top_popular,
        help="Tamaño de la lista de productos populares (fallback).",
    )
    parser.add_argument(
        "--block-size",
        type=int,
        default=DEFAULTS.block_size,
        help="Órdenes por bloque al generar pares (control de memoria).",
    )
    parser.add_argument("--duckdb-memory-limit", default=DEFAULTS.duckdb_memory_limit)
    parser.add_argument(
        "--spill-dir", type=Path, default=Path(DEFAULTS.duckdb_spill_dir)
    )
    parser.add_argument(
        "--tmp-dir",
        type=Path,
        default=Path("/tmp/opencode/nextcart_pairs"),
        help="Directorio temporal para pares intermedios (parquet).",
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
    needed = ["orders", "order_products_prior", "products", "aisles", "departments"]
    missing = [k for k in needed if not paths[k].is_file()]
    if missing:
        sys.exit(
            "ERROR: faltan archivos del dataset para entrenar: "
            + ", ".join(f"{k} ({paths[k]})" for k in missing)
            + "\nDescarga el dataset de Kaggle "
            "(instacart-online-grocery-basket-analysis-dataset) y coloca los CSV "
            f"en '{data_dir}'. Luego reejecuta el comando."
        )
    return paths


def make_views(con: duckdb.DuckDBPyConnection, paths: dict[str, Path]) -> None:
    con.execute(f"""
        CREATE OR REPLACE VIEW orders_v AS
        SELECT order_id, user_id, eval_set, order_number
        FROM read_csv_auto('{paths["orders"]}', header=true)
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW ops_prior_v AS
        SELECT p.order_id, p.product_id
        FROM read_csv_auto('{paths["order_products_prior"]}', header=true) p
        JOIN orders_v o USING(order_id)
        WHERE o.eval_set = 'prior'
    """)
    con.execute(
        f"CREATE OR REPLACE VIEW products_v AS SELECT * FROM read_csv_auto('{paths['products']}', header=true)"
    )
    con.execute(
        f"CREATE OR REPLACE VIEW aisles_v AS SELECT * FROM read_csv_auto('{paths['aisles']}', header=true)"
    )
    con.execute(
        f"CREATE OR REPLACE VIEW departments_v AS SELECT * FROM read_csv_auto('{paths['departments']}', header=true)"
    )


_TRIU_CACHE: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def _triu_for(n: int) -> tuple[np.ndarray, np.ndarray]:
    cached = _TRIU_CACHE.get(n)
    if cached is None:
        cached = np.triu_indices(n, k=1)
        _TRIU_CACHE[n] = cached
    return cached


def pairs_from_baskets(baskets: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Pares (i, j) con i < j de una lista de cestas como arrays ordenados."""
    i_parts: list[np.ndarray] = []
    j_parts: list[np.ndarray] = []
    for arr in baskets:
        n = arr.shape[0]
        if n < 2:
            continue
        ii, jj = _triu_for(n)
        i_parts.append(arr[ii])
        j_parts.append(arr[jj])
    if not i_parts:
        empty = np.empty(0, dtype=np.int32)
        return empty, empty.copy()
    return (
        np.concatenate(i_parts).astype(np.int32, copy=False),
        np.concatenate(j_parts).astype(np.int32, copy=False),
    )


def generate_pairs_blocks(
    con: duckdb.DuckDBPyConnection, tmp_dir: Path, block_size: int, min_support: int
) -> dict[str, int]:
    """Genera pares por bloques de órdenes y los vuelca a parquet comprimido.

    Lectura por bloques (`fetch_record_batch`) para no materializar 32M de filas
    ni los ~150M de pares en memoria.
    """
    ensure_dir(tmp_dir)
    for old in tmp_dir.glob("pairs_*.parquet"):
        old.unlink()
    batch = con.execute(f"""
        SELECT p.order_id, p.product_id
        FROM ops_prior_v p
        WHERE p.product_id IN (SELECT product_id FROM support_v WHERE support >= {min_support})
        ORDER BY p.order_id, p.product_id
    """).to_arrow_reader(batch_size=block_size * 12)

    current_order: int | None = None
    basket: list[int] = []
    block_idx = 0
    i_buf: list[np.ndarray] = []
    j_buf: list[np.ndarray] = []
    rows_read = 0
    baskets_read = 0
    pairs_in_block = 0

    def flush_block() -> None:
        nonlocal block_idx, i_buf, j_buf, pairs_in_block
        if not i_buf:
            return
        ii = np.concatenate(i_buf)
        jj = np.concatenate(j_buf)
        pl.DataFrame({"i": ii, "j": jj}).write_parquet(
            tmp_dir / f"pairs_{block_idx:05d}.parquet", compression="zstd"
        )
        block_idx += 1
        i_buf, j_buf = [], []
        pairs_in_block = 0

    def push_basket() -> None:
        nonlocal i_buf, j_buf, baskets_read, pairs_in_block
        if len(basket) >= 2:
            arr = np.asarray(basket, dtype=np.int32)
            i, j = pairs_from_baskets([arr])
            if i.shape[0]:
                i_buf.append(i)
                j_buf.append(j)
                pairs_in_block += int(i.shape[0])
            baskets_read += 1
        if pairs_in_block >= 12_000_000:
            flush_block()

    try:
        for arrow_batch in batch:
            df = arrow_batch.to_pandas()
            for order_id, product_id in zip(df["order_id"], df["product_id"]):
                rows_read += 1
                if current_order is None:
                    current_order = order_id
                if order_id != current_order:
                    push_basket()
                    basket = []
                    current_order = order_id
                basket.append(int(product_id))
    finally:
        pass
    if basket:
        push_basket()
    flush_block()
    return {
        "rows_read": rows_read,
        "baskets_with_pairs": baskets_read,
        "pair_files": block_idx,
    }


def train_model(data_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    paths = require_files(Path(data_dir))
    con = connect(args)
    make_views(con, paths)
    t_start = time.perf_counter()

    with StepTimer("Soporte global de productos y nº de cestas"):
        n_baskets = int(
            con.execute("SELECT count(DISTINCT order_id) FROM ops_prior_v").fetchone()[
                0
            ]
        )
        n_rows = int(con.execute("SELECT count(*) FROM ops_prior_v").fetchone()[0])
        if n_baskets == 0:
            raise SystemExit("No hay órdenes prior en el dataset: nada que entrenar.")
        con.execute(f"""
            CREATE OR REPLACE TABLE support_v AS
            SELECT product_id, count(*) AS support
            FROM ops_prior_v GROUP BY 1
            HAVING count(*) >= {args.min_support}
        """)
        n_eligible = int(con.execute("SELECT count(*) FROM support_v").fetchone()[0])

    with StepTimer("Popularidad global con recencia (posición relativa de la orden)"):
        con.execute("""
            CREATE OR REPLACE TABLE popular_v AS
            SELECT p.product_id,
                   count(*) AS cnt,
                   avg(o.order_number::DOUBLE / u.n_orders) AS recency_mean
            FROM ops_prior_v p
            JOIN orders_v o USING(order_id)
            JOIN (SELECT user_id, count(*) AS n_orders FROM orders_v
                  WHERE eval_set = 'prior' GROUP BY 1) u USING(user_id)
            GROUP BY 1
        """)
        pop_rows = con.execute(f"""
            SELECT product_id, cnt, recency_mean,
                   ln(1 + cnt) * (0.5 + recency_mean) AS score
            FROM popular_v
            ORDER BY score DESC, product_id ASC
            LIMIT {args.top_popular}
        """).fetchall()
    max_score = max((r[3] for r in pop_rows), default=1.0) or 1.0
    popular_products = [
        {
            "product_id": int(r[0]),
            "count": int(r[1]),
            "recency_mean": round(float(r[2]), 4),
            "score": round(float(r[3]) / max_score, 6),
        }
        for r in pop_rows
    ]

    with StepTimer("Generación de pares por bloques (parquet temporal)"):
        tmp_dir = Path(args.tmp_dir)
        pair_stats = generate_pairs_blocks(
            con, tmp_dir, args.block_size, args.min_support
        )
        log_step(f"Pares generados: {pair_stats}")

    with StepTimer("Agregación de pares y reglas top-K por antecedente"):
        con.execute(f"""
            CREATE OR REPLACE TABLE pair_counts AS
            SELECT i, j, count(*) AS c
            FROM read_parquet('{tmp_dir}/pairs_*.parquet')
            GROUP BY 1, 2
            HAVING count(*) >= {args.min_support}
        """)
        n_pairs_kept = int(
            con.execute("SELECT count(*) FROM pair_counts").fetchone()[0]
        )
        con.execute(f"""
            CREATE OR REPLACE TABLE antecedents_v AS
            SELECT product_id FROM support_v
            ORDER BY support DESC, product_id ASC
            LIMIT {args.max_antecedents}
        """)
        rules_rows = con.execute(f"""
            SELECT pc.i, pc.j, pc.c,
                   pc.c::DOUBLE / si.support AS confidence,
                   (pc.c::DOUBLE * {n_baskets}) / (si.support * sj.support) AS lift
            FROM pair_counts pc
            JOIN support_v si ON pc.i = si.product_id
            JOIN support_v sj ON pc.j = sj.product_id
            WHERE pc.i IN (SELECT product_id FROM antecedents_v)
            QUALIFY row_number() OVER (PARTITION BY pc.i ORDER BY pc.c DESC, pc.j ASC)
                    <= {args.top_k}
        """).fetchall()

    association_rules: dict[str, list[list[Any]]] = defaultdict(list)
    for i, j, c, conf, lift in rules_rows:
        association_rules[str(int(i))].append(
            [int(j), int(c), round(float(conf), 5), round(float(lift), 3)]
        )
    n_rules = sum(len(v) for v in association_rules.values())

    with StepTimer("Metadatos de catálogo"):
        products = con.execute("""
            SELECT p.product_id, p.aisle_id, p.department_id, p.product_name,
                   a.aisle, d.department
            FROM products_v p
            LEFT JOIN aisles_v a USING(aisle_id)
            LEFT JOIN departments_v d USING(department_id)
        """).fetchall()
        catalog_products = {
            str(int(r[0])): {
                "aisle_id": int(r[1]),
                "department_id": int(r[2]),
                "product_name": str(r[3]),
            }
            for r in products
        }
        aisles = {
            str(int(r[0])): str(r[1])
            for r in con.execute("SELECT * FROM aisles_v").fetchall()
        }
        departments = {
            str(int(r[0])): str(r[1])
            for r in con.execute("SELECT * FROM departments_v").fetchall()
        }

    wall = time.perf_counter() - t_start
    trained_at = now_utc_iso()
    model: dict[str, Any] = {
        "model_version": f"0.1.0+{trained_at.replace('-', '').replace(':', '')}",
        "trained_at_utc": trained_at,
        "algorithm": MODEL_ALGORITHM,
        "format_version": MODEL_FORMAT_VERSION,
        "status": MODEL_STATUS_CANDIDATE,
        "parameters": {
            "seed": args.seed,
            "min_support": args.min_support,
            "top_k_rules": args.top_k,
            "max_antecedents": args.max_antecedents,
            "top_popular": args.top_popular,
            "block_size": args.block_size,
            "history_items_used": DEFAULTS.history_items_used,
            "pop_weight": DEFAULTS.pop_weight,
            "repeat_boost": DEFAULTS.repeat_boost,
            "nav_weight": DEFAULTS.nav_weight,
            "rejection_penalty": DEFAULTS.rejection_penalty,
            "lift_cap": DEFAULTS.lift_cap,
            "rule_fields": RULE_FIELDS,
            "score_formula": (
                "score(j) = max_{i en contexto} confidence(i->j) "
                "+ pop_weight * popularidad_normalizada(j) "
                "+ repeat_boost * popularidad_normalizada(j) si j ya comprado; "
                "lift se informa como razón y se limita a lift_cap en inferencia; "
                "los rechazados se penalizan con rejection_penalty y se excluyen; "
                "navegación view contribuye con nav_weight"
            ),
            "training_split": "ordenes eval_set='prior' exclusivamente",
        },
        "training_statistics": {
            "n_baskets_prior": n_baskets,
            "n_rows_prior": n_rows,
            "n_products_eligible": n_eligible,
            "n_distinct_pairs_kept": n_pairs_kept,
            "n_rules": n_rules,
            "n_antecedents": len(association_rules),
            "pair_generation": pair_stats,
            "wall_seconds": round(wall, 1),
        },
        "popular_products": popular_products,
        "association_rules": dict(association_rules),
        "catalog_metadata": {
            "products": catalog_products,
            "aisles": aisles,
            "departments": departments,
        },
    }
    con.close()
    return model


def validate_model(model: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not model["popular_products"]:
        issues.append("popular_products vacío")
    scores = [p["score"] for p in model["popular_products"]]
    if scores != sorted(scores, reverse=True):
        issues.append("popular_products no está ordenado por score descendente")
    if any(not math.isfinite(s) or s < 0 for s in scores):
        issues.append("scores de popularidad no finitos o negativos")
    if any(p["product_id"] <= 0 for p in model["popular_products"]):
        issues.append("popular_products con IDs no positivos")
    if not model["association_rules"]:
        issues.append("association_rules vacío: sin señal de coocurrencia")
    sample_keys = list(model["association_rules"])[:200]
    for key in sample_keys:
        rules = model["association_rules"][key]
        if len(rules) > model["parameters"]["top_k_rules"] + 1:
            issues.append(f"antecedente {key} excede top_k_rules")
            break
        for r in rules:
            if len(r) != len(RULE_FIELDS):
                issues.append(f"regla mal formada en antecedente {key}")
                break
            _, _, conf, lift = r
            if not (0 < conf <= 1.0 + 1e-9) or lift <= 0:
                issues.append(f"confianza/lift fuera de rango en antecedente {key}")
                break
    if not model["catalog_metadata"]["products"]:
        issues.append("catalog_metadata.products vacío")
    return issues


def run_training(
    data_dir: Path,
    output: Path,
    metrics_output: Path | None = None,
    args: argparse.Namespace | None = None,
) -> dict[str, Any]:
    if args is None:
        args = parse_args([])
        args.data_dir = data_dir
        args.output = output
        args.metrics_output = metrics_output
    model = train_model(data_dir, args)

    with StepTimer("Validación del modelo antes de guardarlo"):
        issues = validate_model(model)
        if issues:
            model["status"] = MODEL_STATUS_EXPERIMENTAL
            model["training_statistics"]["validation_issues"] = issues
            log_step(
                "El modelo NO supera los criterios mínimos: se guarda como "
                f"experimental. Problemas: {issues}"
            )
        else:
            log_step("Validación superada: modelo marcado como candidate.")

    with StepTimer("Escritura del artefacto y manifiesto"):
        ensure_dir(Path(output).parent)
        write_json_atomic(output, model, indent=None)
        size_mb = Path(output).stat().st_size / 1e6
        manifest_path = write_manifest(
            output,
            model,
            source_dataset="instacart-online-grocery-basket-analysis-dataset",
            audit_results_path="../reports/audit_results.json",
            metrics_path=str(metrics_output) if metrics_output else None,
        )
        log_step(
            f"Modelo guardado en {output.resolve()} ({size_mb:.1f} MB), "
            f"estado={model['status']}"
        )
        log_step(f"Manifiesto: {manifest_path.resolve()}")

    if metrics_output is not None:
        payload = {
            "stage": "training",
            "generated_at_utc": now_utc_iso(),
            "model_version": model["model_version"],
            "model_status": model["status"],
            "model_path": str(output),
            "training_statistics": model["training_statistics"],
            "note": "La evaluación offline completa la escribe src/evaluate_agent.py "
            "sobre este mismo archivo.",
        }
        write_json_atomic(metrics_output, payload)
        log_step(f"Estadísticas de entrenamiento en {metrics_output.resolve()}")
    return model


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_dir = resolve_data_dir(args.data_dir)
    log_step(f"Directorio de datos: {data_dir}")
    run_training(data_dir, args.output, args.metrics_output, args=args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
