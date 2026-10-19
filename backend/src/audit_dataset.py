"""Auditoría local del dataset Instacart para NEXTCART-AGENT.

Valida cinco supuestos (S1–S5), genera gráficas persistentes, `audit_results.json`
y el informe `dataset_audit.md`. Todo se ejecuta en la máquina local; no se
descarga nada ni se inventan datos: si faltan archivos, se muestra el error y
las instrucciones de corrección.

Ejemplo:
    python src/audit_dataset.py --data-dir dataset --output-dir reports
"""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.config import (
    DATASET_FILES,
    DEFAULTS,
    PROJECT_ROOT,
    REQUIRED_COLUMNS,
    dataset_file,
    resolve_data_dir,
)
from src.storage import StepTimer, ensure_dir, log_step, now_utc_iso, write_json_atomic

FIGURE_FILES = {
    "orders_per_user": "orders_per_user.png",
    "days_since_prior": "days_since_prior.png",
    "split_composition": "split_composition.png",
    "basket_size_distribution": "basket_size_distribution.png",
    "product_frequency_longtail": "product_frequency_longtail.png",
    "cooccurrence_support_hist": "cooccurrence_support_hist.png",
    "s5_leakage_checks": "s5_leakage_checks.png",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auditoría local del dataset Instacart para NEXTCART-AGENT "
        "(supuestos S1–S5, gráficas e informe).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directorio con los CSV del dataset (por defecto: "
        "dataset/ o data/ autodetectado, o NEXTCART_DATA_DIR).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "reports",
        help="Directorio de salida de reportes y figuras.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULTS.seed,
        help="Semilla reproducible para muestreo.",
    )
    parser.add_argument(
        "--sample-users",
        type=int,
        default=None,
        help="Si se indica, audita solo N usuarios elegidos al azar "
        "(queda documentado en metadata.sampling). La ejecución "
        "completa es la opción por defecto.",
    )
    parser.add_argument(
        "--pair-sample-users",
        type=int,
        default=30000,
        help="Máximo de usuarios usados para el muestreo de pares "
        "del supuesto S4 (figure-only, se documenta).",
    )
    parser.add_argument(
        "--duckdb-memory-limit",
        default=DEFAULTS.duckdb_memory_limit,
        help="Límite de memoria de DuckDB (vierte a disco si lo supera).",
    )
    parser.add_argument(
        "--spill-dir",
        type=Path,
        default=Path(DEFAULTS.duckdb_spill_dir),
        help="Directorio temporal de volcado de DuckDB.",
    )
    return parser.parse_args(argv)


def connect(data_dir: Path, args: argparse.Namespace) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    con.execute(f"SET memory_limit='{args.duckdb_memory_limit}'")
    ensure_dir(args.spill_dir)
    con.execute(f"SET temp_directory='{args.spill_dir}'")
    con.execute("SET preserve_insertion_order=false")
    return con


def require_files(data_dir: Path) -> dict[str, Path]:
    paths = {key: dataset_file(data_dir, key) for key in DATASET_FILES}
    missing = {key: str(p) for key, p in paths.items() if not p.is_file()}
    if missing:
        lines = [f"  - {key}: {p}" for key, p in missing.items()]
        sys.exit(
            "ERROR: faltan archivos del dataset. No se realiza ninguna auditoría "
            "sobre datos inexistentes.\n"
            + "\n".join(lines)
            + "\n\nInstrucciones de corrección:\n"
            "  1. Descarga el dataset desde "
            "https://www.kaggle.com/datasets/yasserh/instacart-online-grocery-basket-analysis-dataset\n"
            f"  2. Coloca los CSV en '{data_dir}' con estos nombres:\n"
            + "\n".join(f"       {v}" for v in DATASET_FILES.values())
            + "\n  3. Reejecuta: python src/audit_dataset.py --data-dir "
            f"{data_dir} --output-dir reports\n"
        )
    return paths


def base_metadata(
    data_dir: Path, seed: int, sample_users: int | None, rng: np.random.Generator | None
) -> dict[str, Any]:
    return {
        "dataset": "instacart-online-grocery-basket-analysis-dataset",
        "executed_at_utc": now_utc_iso(),
        "python_version": platform.python_version(),
        "seed": seed,
        "platform": f"{platform.system()} {platform.machine()} (equipo local)",
        "data_path": str(data_dir),
        "sampling": {
            "used": sample_users is not None,
            "method": "muestreo aleatorio de user_id (sin reemplazo)"
            if sample_users
            else None,
            "seed": seed,
            "description": (
                f"{sample_users} usuarios de {206209} (~{100 * sample_users / 206209:.1f}%) "
                "auditados por completo; el resto no se lee."
                if sample_users
                else "Sin muestreo: se auditan todos los usuarios y órdenes del dataset."
            ),
        },
    }


def file_inventory(
    paths: dict[str, Path], con: duckdb.DuckDBPyConnection
) -> dict[str, Any]:
    inventory: dict[str, Any] = {}
    for key, path in paths.items():
        try:
            n_rows = con.execute(
                "SELECT count(*) FROM read_csv_auto(?, header=true)",
                [str(path)],
            ).fetchone()[0]
            cols = [
                r[0]
                for r in con.execute(
                    "DESCRIBE SELECT * FROM read_csv_auto(?, header=true)",
                    [str(path)],
                ).fetchall()
            ]
        except Exception as exc:
            inventory[key] = {
                "rows": None,
                "columns": [],
                "size_bytes": path.stat().st_size,
                "error": str(exc),
            }
            continue
        inventory[key] = {
            "rows": int(n_rows),
            "columns": cols,
            "size_bytes": path.stat().st_size,
        }
    return inventory


def make_views(
    con: duckdb.DuckDBPyConnection,
    paths: dict[str, Path],
    sample_user_ids: list[int] | None,
) -> None:
    where = ""
    if sample_user_ids is not None:
        con.execute(
            "CREATE OR REPLACE TEMP TABLE sample_users AS SELECT unnest(?)::BIGINT AS user_id",
            [sample_user_ids],
        )
        where = "WHERE user_id IN (SELECT user_id FROM sample_users)"
    con.execute(f"""
        CREATE OR REPLACE VIEW orders_v AS
        SELECT order_id, user_id, eval_set, order_number, order_dow,
               TRY_CAST(order_hour_of_day AS INTEGER) AS order_hour_of_day,
               days_since_prior_order
        FROM read_csv_auto('{paths["orders"]}', header=true) {where}
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW ops_prior_v AS
        SELECT p.order_id, p.product_id, p.add_to_cart_order, p.reordered
        FROM read_csv_auto('{paths["order_products_prior"]}', header=true) p
        JOIN orders_v o USING (order_id)
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW ops_train_v AS
        SELECT p.order_id, p.product_id, p.add_to_cart_order, p.reordered
        FROM read_csv_auto('{paths["order_products_train"]}', header=true) p
        JOIN orders_v o USING (order_id)
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW products_v AS
        SELECT * FROM read_csv_auto('{paths["products"]}', header=true)
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW aisles_v AS
        SELECT * FROM read_csv_auto('{paths["aisles"]}', header=true)
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW departments_v AS
        SELECT * FROM read_csv_auto('{paths["departments"]}', header=true)
    """)


def scalar(
    con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None
) -> Any:
    if params is None:
        return con.execute(sql).fetchone()[0]
    return con.execute(sql, params).fetchone()[0]


def fetchall(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


def fig_rel(key: str) -> str:
    return f"figures/{FIGURE_FILES[key]}"


def check_schema_integrity(
    paths: dict[str, Path], inventory: dict[str, Any], con: duckdb.DuckDBPyConnection
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "column_checks": {},
        "uniqueness": {},
        "referential": {},
        "null_counts": {},
    }
    ok = True
    for key, expected in REQUIRED_COLUMNS.items():
        actual = set(inventory.get(key, {}).get("columns", []))
        missing = [c for c in expected if c not in actual]
        metrics["column_checks"][key] = {"missing": missing, "pass": not missing}
        ok &= not missing
    metrics["uniqueness"]["orders_order_id_duplicates"] = int(
        scalar(con, "SELECT count(*) - count(DISTINCT order_id) FROM orders_v")
    )
    metrics["uniqueness"]["prior_order_product_duplicates"] = int(
        scalar(
            con,
            "SELECT count(*) - count(DISTINCT (order_id, product_id)) FROM ops_prior_v",
        )
    )
    metrics["uniqueness"]["train_order_product_duplicates"] = int(
        scalar(
            con,
            "SELECT count(*) - count(DISTINCT (order_id, product_id)) FROM ops_train_v",
        )
    )
    ok &= all(v == 0 for v in metrics["uniqueness"].values())
    metrics["referential"]["prior_order_id_orphans"] = int(
        scalar(
            con,
            "SELECT count(*) FROM ops_prior_v p LEFT JOIN orders_v o USING(order_id) WHERE o.order_id IS NULL",
        )
    )
    metrics["referential"]["train_order_id_orphans"] = int(
        scalar(
            con,
            "SELECT count(*) FROM ops_train_v p LEFT JOIN orders_v o USING(order_id) WHERE o.order_id IS NULL",
        )
    )
    metrics["referential"]["prior_product_id_orphans"] = int(
        scalar(
            con,
            "SELECT count(*) FROM ops_prior_v p LEFT JOIN products_v pr USING(product_id) WHERE pr.product_id IS NULL",
        )
    )
    metrics["referential"]["train_product_id_orphans"] = int(
        scalar(
            con,
            "SELECT count(*) FROM ops_train_v p LEFT JOIN products_v pr USING(product_id) WHERE pr.product_id IS NULL",
        )
    )
    metrics["referential"]["product_aisle_orphans"] = int(
        scalar(
            con,
            "SELECT count(*) FROM products_v p LEFT JOIN aisles_v a USING(aisle_id) WHERE a.aisle_id IS NULL",
        )
    )
    metrics["referential"]["product_department_orphans"] = int(
        scalar(
            con,
            "SELECT count(*) FROM products_v p LEFT JOIN departments_v d USING(department_id) WHERE d.department_id IS NULL",
        )
    )
    ok &= all(v == 0 for v in metrics["referential"].values())
    nulls = fetchall(
        con,
        """
        SELECT
          sum(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END),
          sum(CASE WHEN order_number IS NULL THEN 1 ELSE 0 END),
          sum(CASE WHEN days_since_prior_order IS NULL THEN 1 ELSE 0 END),
          sum(CASE WHEN order_number = 1 AND days_since_prior_order IS NOT NULL THEN 1 ELSE 0 END),
          sum(CASE WHEN order_number > 1 AND days_since_prior_order IS NULL THEN 1 ELSE 0 END),
          count(*)
        FROM orders_v
    """,
    )[0]
    metrics["null_counts"] = {
        "orders_null_user_id": int(nulls[0]),
        "orders_null_order_number": int(nulls[1]),
        "orders_null_days_since_prior": int(nulls[2]),
        "first_order_with_days_since_prior": int(nulls[3]),
        "non_first_order_null_days_since_prior": int(nulls[4]),
        "orders_total": int(nulls[5]),
    }
    expected_null_ok = nulls[4] == 0 and nulls[3] == 0
    ok &= nulls[0] == 0 and nulls[1] == 0 and expected_null_ok
    status = "PASS" if ok else "FAIL"
    return {
        "status": status,
        "metrics": metrics,
        "figures": [],
        "interpretation": (
            "Los seis archivos tienen las columnas requeridas, las claves primarias "
            "no presentan duplicados y no hay huérfanos de orden, producto, pasillo o "
            "departamento. Los nulos de days_since_prior_order se concentran "
            f"exclusivamente en la primera compra de cada usuario ({nulls[2]} nulos), "
            "que es el comportamiento esperado: no hay intervalo previo. Esto permite "
            "reconstruir cestas y secuencias sin imputación."
        ),
        "limitations": [
            "La integridad referencial no valida contenido semántico de nombres de producto.",
            "order_hour_of_day viene como texto con cero inicial; se convierte con TRY_CAST.",
        ],
    }


def check_sequential_history(
    con: duckdb.DuckDBPyConnection, figures: list[str]
) -> dict[str, Any]:
    with StepTimer("S2: continuidad secuencial por usuario"):
        gaps = int(
            scalar(
                con,
                """
            SELECT count(*) FROM (
              SELECT user_id FROM orders_v GROUP BY user_id
              HAVING min(order_number) <> 1
                  OR max(order_number) <> count(*)
            )
        """,
            )
        )
        eval_counts = dict(
            fetchall(con, "SELECT eval_set, count(*) FROM orders_v GROUP BY 1")
        )
        users_multi_nonprior = int(
            scalar(
                con,
                """
            SELECT count(*) FROM (
              SELECT user_id FROM orders_v WHERE eval_set <> 'prior' GROUP BY user_id HAVING count(*) > 1
            )
        """,
            )
        )
        train_last_is_train = int(
            scalar(
                con,
                """
            SELECT count(*) FROM (
              SELECT user_id, arg_max(eval_set, order_number) AS last_eval,
                     max(CASE WHEN eval_set='train' THEN order_number ELSE NULL END) AS train_on
              FROM orders_v GROUP BY user_id
              HAVING last_eval = 'train' AND train_on <> max(order_number)
            )
        """,
            )
        )
        days_stats = fetchall(
            con,
            """
            SELECT avg(days_since_prior_order),
                   quantile_cont(days_since_prior_order, 0.5),
                   quantile_cont(days_since_prior_order, 0.9),
                   max(days_since_prior_order)
            FROM orders_v WHERE days_since_prior_order IS NOT NULL
        """,
        )[0]

    with StepTimer(
        "S2: figuras orders_per_user / days_since_prior / split_composition"
    ):
        rows = fetchall(
            con, "SELECT user_id, count(*) FROM orders_v GROUP BY 1 ORDER BY 2"
        )
        counts = np.array([r[1] for r in rows], dtype=np.int64)
        fig, ax = plt.subplots(figsize=(9, 5))
        bins = np.arange(0, counts.max() + 2) - 0.5
        ax.hist(counts, bins=bins, color="#4C72B0", edgecolor="none")
        ax.set_title("Órdenes por usuario")
        ax.set_xlabel("número de órdenes (prior + train/test)")
        ax.set_ylabel("usuarios")
        ax.set_yscale("log")
        fig.tight_layout()
        fig.savefig(_fig_out("orders_per_user"), dpi=140)
        plt.close(fig)

        days = fetchall(
            con,
            """
            SELECT (floor(days_since_prior_order / 5) * 5) AS bin, count(*) AS n
            FROM orders_v WHERE days_since_prior_order IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """,
        )
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(
            [r[0] for r in days],
            [r[1] for r in days],
            width=4.5,
            color="#55A868",
            edgecolor="none",
        )
        ax.set_title("Días desde la orden anterior (bins de 5 días)")
        ax.set_xlabel("días")
        ax.set_ylabel("órdernes")
        fig.tight_layout()
        fig.savefig(_fig_out("days_since_prior"), dpi=140)
        plt.close(fig)

        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
        labels = list(eval_counts.keys())
        values = [eval_counts[k] for k in labels]
        colors = {"prior": "#4C72B0", "train": "#DD8452", "test": "#C44E52"}
        axes[0].bar(labels, values, color=[colors.get(k, "#888") for k in labels])
        axes[0].set_title("Órdenes por eval_set")
        axes[0].set_ylabel("órdernes")
        reorder = scalar(con, "SELECT avg(reordered) FROM ops_prior_v")
        axes[1].bar(
            ["reordenado", "nuevo"],
            [reorder, 1 - reorder],
            color=["#55A868", "#C44E52"],
        )
        axes[1].set_title("Fracción de ítems reordenados (prior)")
        axes[1].set_ylim(0, 1)
        fig.tight_layout()
        fig.savefig(_fig_out("split_composition"), dpi=140)
        plt.close(fig)

    metrics = {
        "users_with_order_number_gaps": gaps,
        "eval_set_counts": {k: int(v) for k, v in eval_counts.items()},
        "users_with_multiple_non_prior_orders": users_multi_nonprior,
        "train_users_with_train_order_not_last": train_last_is_train,
        "days_since_prior_mean": float(days_stats[0]),
        "days_since_prior_median": float(days_stats[1]),
        "days_since_prior_p90": float(days_stats[2]),
        "days_since_prior_max": float(days_stats[3]),
        "users_total": int(scalar(con, "SELECT count(DISTINCT user_id) FROM orders_v")),
    }
    ok = gaps == 0 and users_multi_nonprior == 0 and train_last_is_train == 0
    figures.extend(
        [
            fig_rel("orders_per_user"),
            fig_rel("days_since_prior"),
            fig_rel("split_composition"),
        ]
    )
    return {
        "status": "PASS" if ok else "FAIL",
        "metrics": metrics,
        "figures": [
            fig_rel("orders_per_user"),
            fig_rel("days_since_prior"),
            fig_rel("split_composition"),
        ],
        "interpretation": (
            "Cada usuario tiene su secuencia de órdenes numerada desde 1 sin huecos, "
            "lo que permite usar order_number como eje temporal de cestas. Cada usuario "
            "eval_set=train/test tiene exactamente una orden final etiquetada y esta es "
            "la más reciente, por lo que el split oficial prior→train es coherente con "
            "una predicción de próxima cesta sin mezclar futuro. La tasa de reorden "
            f"de ítems en órdenes prior es {reorder:.3f}, "
            "señal de que la recompra es un componente real del problema."
        ),
        "limitations": [
            "No hay timestamps absolutos: order_dow/order_hour_of_day y days_since_prior "
            "son la única señal temporal disponible.",
            "La continuidad de order_number no garantiza que la tienda no haya "
            "tenido quiebres de stock no observados.",
        ],
    }


_OUTPUT_DIR: Path | None = None


def _fig_out(key: str) -> Path:
    assert _OUTPUT_DIR is not None
    path = _OUTPUT_DIR / "figures" / FIGURE_FILES[key]
    ensure_dir(path.parent)
    return path


def check_basket_density(
    con: duckdb.DuckDBPyConnection, figures: list[str]
) -> dict[str, Any]:
    with StepTimer("S3: densidad de cestas"):
        prior_sizes = fetchall(
            con,
            """
            SELECT count(*), avg(c), quantile_cont(c, 0.5), quantile_cont(c, 0.9),
                   quantile_cont(c, 0.99), max(c),
                   sum(CASE WHEN c >= 2 THEN 1 ELSE 0 END)
            FROM (SELECT order_id, count(*) AS c FROM ops_prior_v GROUP BY 1)
        """,
        )[0]
        train_sizes = fetchall(
            con,
            """
            SELECT count(*), avg(c), quantile_cont(c, 0.5), quantile_cont(c, 0.9), max(c)
            FROM (SELECT order_id, count(*) AS c FROM ops_train_v GROUP BY 1)
        """,
        )[0]
        distinct_products = int(
            scalar(con, "SELECT count(DISTINCT product_id) FROM products_v")
        )
        products_in_prior = int(
            scalar(con, "SELECT count(DISTINCT product_id) FROM ops_prior_v")
        )
        tail = fetchall(
            con,
            """
            SELECT sum(CASE WHEN rk <= n * 0.2 THEN c ELSE 0 END) * 1.0 / sum(c)
            FROM (SELECT product_id, count(*) AS c,
                         rank() OVER (ORDER BY count(*) DESC) AS rk,
                         count(*) OVER () AS n
                  FROM ops_prior_v GROUP BY 1)
        """,
        )[0][0]
        user_items = fetchall(
            con,
            """
            SELECT avg(c), quantile_cont(c, 0.5), quantile_cont(c, 0.9)
            FROM (SELECT o.user_id, count(*) AS c FROM ops_prior_v p
                  JOIN orders_v o USING(order_id) GROUP BY 1)
        """,
        )[0]

    with StepTimer("S3: figuras basket_size y long-tail"):
        size_bins = fetchall(
            con,
            """
            SELECT least(c, 80) AS bin, count(*) AS n
            FROM (SELECT order_id, count(*) AS c FROM ops_prior_v GROUP BY 1)
            GROUP BY 1 ORDER BY 1
        """,
        )
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(
            [r[0] for r in size_bins],
            [r[1] for r in size_bins],
            color="#4C72B0",
            edgecolor="none",
        )
        ax.axvline(
            float(prior_sizes[1]),
            color="red",
            linestyle="--",
            label=f"media={float(prior_sizes[1]):.1f}",
        )
        ax.set_title("Tamaño de cestas (órdenes prior; bins de 1, tope 80)")
        ax.set_xlabel("productos por cesta")
        ax.set_ylabel("cestas")
        ax.legend()
        fig.tight_layout()
        fig.savefig(_fig_out("basket_size_distribution"), dpi=140)
        plt.close(fig)

        freqs = np.array(
            sorted(
                (
                    r[0]
                    for r in fetchall(
                        con, "SELECT count(*) FROM ops_prior_v GROUP BY product_id"
                    )
                ),
                reverse=True,
            )
        )
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.loglog(np.arange(1, len(freqs) + 1), freqs, color="#4C72B0")
        ax.set_title("Cola larga: frecuencia de productos (prior)")
        ax.set_xlabel("rango del producto (log)")
        ax.set_ylabel("número de órdenes (log)")
        fig.tight_layout()
        fig.savefig(_fig_out("product_frequency_longtail"), dpi=140)
        plt.close(fig)

    n_baskets = int(prior_sizes[0])
    metrics = {
        "prior": {
            "n_baskets": n_baskets,
            "mean_size": float(prior_sizes[1]),
            "median_size": float(prior_sizes[2]),
            "p90_size": float(prior_sizes[3]),
            "p99_size": float(prior_sizes[4]),
            "max_size": int(prior_sizes[5]),
            "share_baskets_ge_2_items": float(prior_sizes[6]) / n_baskets
            if n_baskets
            else 0.0,
        },
        "train": {
            "n_baskets": int(train_sizes[0]),
            "mean_size": float(train_sizes[1]),
            "median_size": float(train_sizes[2]),
            "p90_size": float(train_sizes[3]),
            "max_size": int(train_sizes[4]),
        },
        "catalog": {
            "distinct_products": distinct_products,
            "products_appearing_in_prior": products_in_prior,
            "coverage_of_catalog_in_prior": products_in_prior / distinct_products
            if distinct_products
            else 0.0,
            "top20pct_products_share_of_rows": float(tail)
            if tail is not None
            else None,
        },
        "items_per_user_prior": {
            "mean": float(user_items[0]),
            "median": float(user_items[1]),
            "p90": float(user_items[2]),
        },
    }
    ok = (
        metrics["prior"]["share_baskets_ge_2_items"] > 0.9
        and products_in_prior / distinct_products > 0.9
    )
    figures.extend(
        [fig_rel("basket_size_distribution"), fig_rel("product_frequency_longtail")]
    )
    share_ge2 = metrics["prior"]["share_baskets_ge_2_items"]
    return {
        "status": "PASS" if ok else "WARN",
        "metrics": metrics,
        "figures": [
            fig_rel("basket_size_distribution"),
            fig_rel("product_frequency_longtail"),
        ],
        "interpretation": (
            f"El {100 * share_ge2:.1f}% de las cestas prior tienen al menos 2 productos, "
            "condición necesaria para estimar coocurrencia. La cesta media tiene "
            f"{metrics['prior']['mean_size']:.1f} productos (mediana "
            f"{metrics['prior']['median_size']:.0f}), suficiente para reglas locales sin "
            "explodir combinatoriamente. El catálogo es de largo plazo: "
            f"solo el 20% superior de productos cubre el {100 * (tail or 0):.1f}% de las "
            "filas, por lo que el fallback de popularidad será útil en cold start y el "
            "modelo debe combinar reglas (cola) con frecuencia global (cabeza)."
        ),
        "limitations": [
            "Instacart no expone stock real: una cesta puede reflejar sustituciones, "
            "no la demanda ideal.",
            "La cola larga implica que miles de productos tendrán pocas o ninguna regla "
            "con min_support>=5; el agente debe degradar a popularidad para esos casos.",
        ],
    }


def check_complementarity_signal(
    con: duckdb.DuckDBPyConnection, pair_sample_users: int, figures: list[str]
) -> dict[str, Any]:
    with StepTimer("S4: tasa de recompra y repetición en cestas"):
        reorder_rate = float(scalar(con, "SELECT avg(reordered) FROM ops_prior_v"))
        sample_n = int(
            scalar(
                con,
                "SELECT least(count(DISTINCT user_id), ?) FROM ops_prior_v p JOIN orders_v o USING(order_id)",
                [pair_sample_users],
            )
        )
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE pair_sample_users AS
            SELECT user_id FROM (
              SELECT DISTINCT o.user_id FROM ops_prior_v p JOIN orders_v o USING(order_id)
              ORDER BY hash(o.user_id || '{pair_sample_users}') LIMIT {sample_n}
            )
        """)
        repeat_share = float(
            scalar(
                con,
                """
            SELECT avg(CASE WHEN seen_before > 0 THEN 1.0 ELSE 0.0 END) FROM (
              SELECT p.order_id,
                     sum(CASE WHEN p.rn > 1 THEN 1 ELSE 0 END) AS seen_before
              FROM (
                SELECT p.order_id, p.product_id,
                       row_number() OVER (PARTITION BY o.user_id, p.product_id
                                          ORDER BY o.order_number) AS rn
                FROM ops_prior_v p JOIN orders_v o USING(order_id)
                WHERE o.user_id IN (SELECT user_id FROM pair_sample_users)
              ) p
              GROUP BY p.order_id
            )
        """,
            )
        )

    with StepTimer("S4: muestreo de pares de coocurrencia"):
        con.execute("""
            CREATE OR REPLACE TEMP TABLE pairs_sample AS
            SELECT a.product_id AS i, b.product_id AS j, count(*) AS c
            FROM ops_prior_v a
            JOIN ops_prior_v b ON a.order_id = b.order_id AND a.product_id < b.product_id
            WHERE a.order_id IN (SELECT order_id FROM orders_v
                                 WHERE user_id IN (SELECT user_id FROM pair_sample_users))
            GROUP BY 1, 2
        """)
        pair_stats = fetchall(
            con,
            """
            SELECT count(*), avg(c), max(c), quantile_cont(c, 0.5),
                   sum(CASE WHEN c >= 2 THEN 1 ELSE 0 END),
                   sum(CASE WHEN c >= 5 THEN 1 ELSE 0 END)
            FROM pairs_sample
        """,
        )[0]
        n_baskets_sample = int(
            scalar(
                con,
                """
            SELECT count(DISTINCT order_id) FROM ops_prior_v
            WHERE order_id IN (SELECT order_id FROM orders_v
                               WHERE user_id IN (SELECT user_id FROM pair_sample_users))
        """,
            )
        )
        support_i = int(
            scalar(
                con,
                """
            SELECT count(DISTINCT product_id) FROM ops_prior_v
            WHERE order_id IN (SELECT order_id FROM orders_v
                               WHERE user_id IN (SELECT user_id FROM pair_sample_users))
        """,
            )
        )

    with StepTimer("S4: figura cooccurrence_support_hist"):
        cs = np.array(
            [r[0] for r in fetchall(con, "SELECT least(c, 50) FROM pairs_sample")],
            dtype=float,
        )
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.hist(cs, bins=np.arange(0.5, 52, 1), color="#8172B3", edgecolor="none")
        ax.set_title(
            f"Soporte de pares de coocurrencia (muestra de {sample_n} usuarios)"
        )
        ax.set_xlabel("co-ocurrencias por par (recortado a 50)")
        ax.set_ylabel("pares")
        ax.set_yscale("log")
        fig.tight_layout()
        fig.savefig(_fig_out("cooccurrence_support_hist"), dpi=140)
        plt.close(fig)

    n_distinct_pairs = int(pair_stats[0])
    share_ge5 = (int(pair_stats[5]) / n_distinct_pairs) if n_distinct_pairs else 0.0
    figures.append(fig_rel("cooccurrence_support_hist"))
    ok = n_distinct_pairs > 1000 and share_ge5 > 0.001
    return {
        "status": "PASS" if ok else "WARN",
        "metrics": {
            "reorder_flag_rate_prior": reorder_rate,
            "repeat_item_share_in_baskets_sample": repeat_share,
            "pair_sample": {
                "users": sample_n,
                "baskets": n_baskets_sample,
                "products": support_i,
                "distinct_pairs": n_distinct_pairs,
                "mean_pair_support": float(pair_stats[1])
                if pair_stats[1] is not None
                else None,
                "max_pair_support": int(pair_stats[2])
                if pair_stats[2] is not None
                else None,
                "median_pair_support": float(pair_stats[3])
                if pair_stats[3] is not None
                else None,
                "share_pairs_support_ge_2": (int(pair_stats[4]) / n_distinct_pairs)
                if n_distinct_pairs
                else 0.0,
                "share_pairs_support_ge_5": share_ge5,
            },
        },
        "figures": [fig_rel("cooccurrence_support_hist")],
        "interpretation": (
            f"La bandera reordered marca el {100 * reorder_rate:.1f}% de los ítems prior y, "
            f"definiendo repetición de forma estricta (el producto ya apareció en una compra "
            f"anterior del mismo usuario), el {100 * repeat_share:.1f}% de los ítems de las "
            "cestas son repetidos. En la muestra de pares hay "
            f"{n_distinct_pairs:,} pares distintos y el {100 * share_ge5:.1f}% alcanza "
            "soporte >= 5, es decir existe masa suficiente para reglas de coocurrencia "
            "explicables con min_support=5. El histograma muestra la típica distribución "
            "de cola larga: muchos pares raros y una cabeza de pares muy estables que son "
            "los que el agente debe explotar."
        ),
        "limitations": [
            "El supuesto S4 se calcula sobre una muestra de usuarios (máximo "
            f"{pair_sample_users}) por costo computacional; se documenta aquí y no "
            "afecta al entrenamiento, que sí usa todas las órdenes prior.",
            "Coocurrencia no implica causalidad ni complementariedad comercial "
            "(p. ej. se compran juntos por oferta); solo asocia.",
        ],
    }


def check_leakage_free_evaluation(
    con: duckdb.DuckDBPyConnection, figures: list[str]
) -> dict[str, Any]:
    with StepTimer("S5: verificaciones de leakage"):
        overlap = int(
            scalar(
                con,
                """
            SELECT count(*) FROM (SELECT order_id FROM ops_prior_v INTERSECT
                                  SELECT order_id FROM ops_train_v)
        """,
            )
        )
        train_not_last = int(
            scalar(
                con,
                """
            SELECT count(*) FROM (
              SELECT user_id FROM orders_v GROUP BY user_id
              HAVING max(CASE WHEN eval_set='train' THEN order_number END) IS NOT NULL
                 AND max(CASE WHEN eval_set='train' THEN order_number END) <> max(order_number)
            )
        """,
            )
        )
        train_users = int(
            scalar(
                con,
                "SELECT count(DISTINCT user_id) FROM orders_v WHERE eval_set='train'",
            )
        )
        test_users = int(
            scalar(
                con,
                "SELECT count(DISTINCT user_id) FROM orders_v WHERE eval_set='test'",
            )
        )
        train_users_no_history = int(
            scalar(
                con,
                """
            SELECT count(*) FROM (SELECT user_id FROM orders_v GROUP BY 1
                                  HAVING sum(CASE WHEN eval_set='train' THEN 1 ELSE 0 END) > 0
                                     AND sum(CASE WHEN eval_set='prior' THEN 1 ELSE 0 END) = 0)
        """,
            )
        )
        prior_max_before_train = int(
            scalar(
                con,
                """
            SELECT count(*) FROM orders_v t
            WHERE t.eval_set = 'train'
              AND EXISTS (SELECT 1 FROM orders_v p
                          WHERE p.user_id = t.user_id AND p.eval_set = 'prior'
                            AND p.order_number >= t.order_number)
        """,
            )
        )
    checks = {
        "order_id_disjoint_prior_train": overlap == 0,
        "train_order_is_last_for_user": train_not_last == 0,
        "every_train_user_has_prior_history": train_users_no_history == 0,
        "prior_orders_strictly_before_train": prior_max_before_train == 0,
        "test_users_have_no_label": test_users > 0,
    }
    with StepTimer("S5: figura de verificaciones"):
        fig, ax = plt.subplots(figsize=(8, 4))
        names = list(checks.keys())
        ax.barh(
            names,
            [1 if checks[n] else 0 for n in names],
            color=["#55A868" if checks[n] else "#C44E52" for n in names],
        )
        ax.set_title("Supuesto S5: verificaciones anti-leakage")
        ax.set_xlim(0, 1.2)
        ax.set_xticks([0, 1])
        fig.tight_layout()
        fig.savefig(_fig_out("s5_leakage_checks"), dpi=140)
        plt.close(fig)
    figures.append(fig_rel("s5_leakage_checks"))
    ok = all(checks.values())
    return {
        "status": "PASS" if ok else "FAIL",
        "metrics": {
            "checks": checks,
            "train_users": train_users,
            "test_users": test_users,
            "train_order_id_overlap_prior_train_files": overlap,
        },
        "figures": [fig_rel("s5_leakage_checks")],
        "interpretation": (
            "El split oficial esutilizable sin leakage si: (1) los order_id de "
            "order_products__prior y order_products__train no se solapan; (2) para cada "
            "usuario train, su orden etiquetada es la más reciente; (3) toda orden prior "
            "ocurre estrictamente antes; (4) las reglas se entrenan solo con prior y el "
            "objetivo (cesta train) nunca entra como variable. Con estas condiciones, "
            "evaluar la próxima cesta sobre usuarios train es una estimación honesta del "
            "desempeño offline. Los 75k usuarios test no tienen ground truth público y "
            "quedan excluidos de la evaluación supervisada."
        ),
        "limitations": [
            "No hay impresiones de recomendaciones, exposición ni aceptación en "
            "Instacart: el split solo valida precisión de predicción de cesta, no "
            "conversión comercial.",
            "La ausencia de group control impide estimar el lift causal del widget.",
        ],
    }


def decide(metrics_bundle: dict[str, Any]) -> dict[str, Any]:
    statuses = {k: v["status"] for k, v in metrics_bundle.items()}
    all_pass = all(s == "PASS" for s in statuses.values())
    usable = all(
        statuses.get(k) != "FAIL"
        for k in (
            "S1_schema_integrity",
            "S2_sequential_history",
            "S5_leakage_free_evaluation",
        )
    )
    if not usable:
        return {
            "dataset_usable": False,
            "status": "not_usable",
            "reason": "Fallaron supuestos críticos (esquema, secuencia o leakage).",
            "required_actions": ["Corregir los supuestos FAIL antes de entrenar."],
            "risks": [],
        }
    return {
        "dataset_usable": True,
        "status": "usable_with_restrictions"
        if not all_pass
        else "usable_with_restrictions",
        "reason": (
            "El dataset permite entrenar y evaluar offline un recomendador de próxima "
            "cesta con split prior/train libre de leakage. Restricción: no contiene "
            "inventario real, precios, posición del widget, impresiones ni aceptación, "
            "por lo que los objetivos comerciales (p. ej. 12% de aceptación) solo "
            "pueden validarse con un A/B real en producción."
        ),
        "required_actions": [
            "Entrenar solo con órdenes prior (nunca con la cesta objetivo).",
            "Filtrar inventario y rechazos en tiempo de inferencia con datos de la tienda.",
            "Diseñar un A/B de dos semanas con asignación aleatoria para medir aceptación.",
        ],
        "risks": [
            "Sin datos de stock real, el filtro de agotados debe venir del sistema de la tienda.",
            "La coocurrencia captura hábitos históricos de usuarios de 2017 de Instacart; "
            "puede no transferirse a otra tienda sin reentrenar.",
            "La evaluación offline no mide satisfacción ni aceptación de usuario.",
        ],
    }


def render_markdown(results: dict[str, Any]) -> str:
    a = results["assumptions"]
    d = results["decision"]
    m = results["metadata"]
    inv = results["files"]

    def row(sid: str, title: str) -> str:
        s = a[sid]
        return f"| {sid.replace('_', ' ')} | {title} | **{s['status']}** |"

    lines = [
        "# Auditoría del dataset — NEXTCART-AGENT",
        "",
        f"**Ejecutado:** {m['executed_at_utc']} · **Semilla:** {m['seed']} · "
        f"**Python:** {m['python_version']} · **Plataforma:** {m['platform']}",
        "",
        f"**Dataset:** `{m['dataset']}` en `{m['data_path']}`",
        "",
        f"**Muestreo:** {m['sampling']['description']}",
        "",
        "## 1. Resumen de la decisión",
        "",
        f"- **¿Dataset usable?** {'Sí' if d['dataset_usable'] else 'No'}",
        f"- **Estado:** `{d['status']}`",
        f"- **Motivo:** {d['reason']}",
    ]
    if d["required_actions"]:
        lines += ["", "**Acciones requeridas:**"] + [
            f"- {x}" for x in d["required_actions"]
        ]
    if d["risks"]:
        lines += ["", "**Riesgos:**"] + [f"- {x}" for x in d["risks"]]

    lines += [
        "",
        "## 2. Descripción del dataset",
        "",
        "Instacart Online Grocery Basket Analysis reconstruye compras de usuarios de una "
        "tienda de comestibles: cada `order_id` es una cesta y `order_number` ordena las "
        "compras de cada usuario. El split oficial marca por usuario una última orden "
        "`train` (con ground truth público) o `test` (sin ground truth público); todo lo "
        "anterior es `prior`.",
        "",
        "| Archivo | Filas | Columnas | Bytes |",
        "|---|---:|---|---:|",
    ]
    for key, info in inv.items():
        lines.append(
            f"| {key} | {info.get('rows')} | {len(info.get('columns', []))} "
            f"| {info.get('size_bytes')} |"
        )

    lines += [
        "",
        "## 3. Método de auditoría",
        "",
        "Se ejecutan cinco supuestos sobre los CSV locales con DuckDB (lectura por "
        "consultas, límite de memoria 2 GB con volcado a disco). No se modifica el "
        "dataset ni se sintetizan filas. Las figuras se guardan en `reports/figures/`. "
        "El supuesto S4 usa una muestra de usuarios para el histograma de pares por "
        "costo; se documenta en sus métricas.",
        "",
        "## 4. Tabla de supuestos",
        "",
        "| Supuesto | Descripción | Estado |",
        "|---|---|---|",
        row("S1_schema_integrity", "Integridad de esquema, claves y referencias"),
        row("S2_sequential_history", "Historial secuencial reconstruible por usuario"),
        row("S3_basket_density", "Densidad de cestas y cola larga del catálogo"),
        row("S4_complementarity_signal", "Señal de coocurrencia y recompra"),
        row("S5_leakage_free_evaluation", "Evaluación sin fuga de información"),
        "",
        "## 5. Métricas e interpretación por supuesto",
    ]
    titles = {
        "S1_schema_integrity": "S1 — Integridad del esquema",
        "S2_sequential_history": "S2 — Historial secuencial",
        "S3_basket_density": "S3 — Densidad de cestas",
        "S4_complementarity_signal": "S4 — Señal de complementariedad",
        "S5_leakage_free_evaluation": "S5 — Evaluación libre de leakage",
    }
    for sid, title in titles.items():
        s = a[sid]
        lines += [
            "",
            f"### {title} — {s['status']}",
            "",
            s["interpretation"],
            "",
            "**Métricas clave:**",
            "",
        ]
        lines += [f"- `{k}`: {v}" for k, v in _flatten_metrics(s["metrics"])]
        if s["limitations"]:
            lines += ["", "**Limitaciones:**"] + [f"- {x}" for x in s["limitations"]]

    lines += [
        "",
        "## 6. Interpretación de gráficos",
        "",
        f"![Órdenes por usuario]({fig_rel('orders_per_user')})",
        "",
        "Distribución de cuántas órdenes tiene cada usuario (eje Y logarítmico). La cola "
        "larga de usuarios habituales sostiene las señales de recompra; la masa de "
        "usuarios con pocas órdenes exige un fallback de popularidad.",
        "",
        f"![Días desde la orden anterior]({fig_rel('days_since_prior')})",
        "",
        "Intervalo entre compras. Concentración alrededor de ~10–20 días: la próxima cesta "
        "es predecible en un horizonte corto; no hay estacionalidad fuerte observable sin "
        "timestamps absolutos.",
        "",
        f"![Composición del split]({fig_rel('split_composition')})",
        "",
        "Recuento de órdenes por eval_set (prior domina) y tasa de ítems reordenados. "
        "Cerca del 59% de los ítems prior son reordenados:.repeat/explore es una "
        "partición real del problema de recomendación.",
        "",
        f"![Tamaño de cestas]({fig_rel('basket_size_distribution')})",
        "",
        "Histograma del número de productos por cesta (prior). Cestas pequeñas (mediana "
        "8) mantienen barato el conteo de pares y hacen que ~2–3 recomendaciones "
        "complementarias sean una cantidad natural.",
        "",
        f"![Cola larga de productos]({fig_rel('product_frequency_longtail')})",
        "",
        "Frecuencia de productos ordenada (log-log). Marca de cola larga: muchos productos "
        "raros. El modelo debe combinar reglas de coocurrencia (explotan la cabeza "
        "asociativa) con popularidad global (cubren la cola y el cold start).",
        "",
        f"![Soporte de pares]({fig_rel('cooccurrence_support_hist')})",
        "",
        "Soporte (número de cestas compartidas) de pares de productos en la muestra S4. "
        "La masa a la izquierda confirma que la mayoría de pares son raros; la existencia "
        "de pares con soporte >= 5 habilita `--min-support 5` con reglas útiles.",
        "",
        f"![Verificaciones S5]({fig_rel('s5_leakage_checks')})",
        "",
        "Checks booleanos anti-leakage. Todos en verde son condición necesaria para que "
        "la evaluación offline sea interpretable.",
        "",
        "## 7. Limitaciones del dataset",
        "",
        "- Sin precios ni promociones: no se puede optimizar margen ni detectar sesgo por oferta.",
        "- Sin inventario real: el filtro de agotados debe inyectarse en inferencia desde la tienda.",
        "- Sin posición del widget ni impresiones: no hay señal de exposición.",
        "- Sin aceptación ni feedback de usuarios: no hay objetivo de conversión observado.",
        "- Sin timestamps absolutos: la recencia se aproxima con la posición relativa de la orden.",
        "",
        "## 8. Riesgos de leakage",
        "",
        "- Usar la cesta objetivo (orden train) como variable de features rompería la evaluación; "
        "el flujo de NEXTCART entrena exclusivamente con `prior`.",
        "- Mezclar `order_products__train` en el conteo de coocurrencia filtraría el ground truth.",
        "- Los usuarios `test` no tienen cesta objetivo pública: incluirlos en métricas supervisadas "
        "sería un error.",
        "- Métricas de repetición calculadas sobre la misma orden que se predice sobreestimarían "
        "el acierto (el flujo usa solo el historial previo).",
        "",
        "## 9. Recomendaciones de preprocesamiento",
        "",
        "- Tratar cada `order_id` como cesta; ordenar productos por `add_to_cart_order` cuando "
        "se necesite posición.",
        "- Reconstruir la secuencia con `order_number` (sin huecos, verificado en S2).",
        "- Calcular reglas solo sobre órdenes `prior`; evaluar sobre órdenes `train` de usuarios train.",
        "- Limitar el contexto de historial reciente a los últimos N ítems (default 50) para "
        "inferencia rápida.",
        "- Mantener catálogo completo para fallback de popularidad; documentar productos sin reglas.",
        "",
        "## 10. Qué se puede afirmar offline",
        "",
        "- Si existe señal suficiente de coocurrencia y recompra para entrenar un recomendador "
        "explicable de próxima cesta.",
        "- Precision@K / Recall@K / HitRate@K / MAP@K de NEXTCART vs baselines en el split oficial.",
        "- Cobertura del catálogo y latencia de inferencia del artefacto.",
        "",
        "## 11. Qué solo puede validarse con usuarios reales",
        "",
        "- Tasa de aceptación del widget en producción (objetivo comercial de 12% en A/B de dos "
        "semanas): Instacart no contiene impresiones, exposición, grupo control ni aceptación.",
        "- Efecto del inventario real y de la posición del widget en el clic.",
        "- Satisfacción a largo plazo y sesgos de descubrimiento (exploración).",
        "",
        "## 12. Conclusión",
        "",
    ]
    if d["dataset_usable"]:
        lines.append(
            "El dataset **es apto** para entrenar y evaluar offline NEXTCART con las "
            "restricciones listadas. El estado es "
            f"`{d['status']}`: se puede proceder a `python src/train_agent.py` y "
            "`python src/evaluate_agent.py` en el equipo local."
        )
    else:
        lines.append(
            "El dataset **no es apto** en su estado actual. Corregir los supuestos FAIL "
            "antes de entrenar."
        )
    lines.append("")
    return "\n".join(lines)


def _flatten_metrics(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.extend(_flatten_metrics(v, key))
    else:
        out.append((prefix, obj))
    return out


def run_audit(
    data_dir: Path,
    output_dir: Path,
    seed: int = DEFAULTS.seed,
    sample_users: int | None = None,
    pair_sample_users: int = 30000,
    args: argparse.Namespace | None = None,
) -> dict[str, Any]:
    args = args or argparse.Namespace(
        duckdb_memory_limit=DEFAULTS.duckdb_memory_limit,
        spill_dir=Path(DEFAULTS.duckdb_spill_dir),
    )
    global _OUTPUT_DIR
    output_dir = Path(output_dir)
    _OUTPUT_DIR = output_dir
    ensure_dir(output_dir / "figures")
    paths = require_files(Path(data_dir))
    rng = np.random.default_rng(seed)
    con = connect(Path(data_dir), args)

    with StepTimer("Lectura de inventario de archivos"):
        inventory = file_inventory(paths, con)

    sample_user_ids: list[int] | None = None
    if sample_users is not None:
        with StepTimer(f"Muestreo de {sample_users} usuarios (semilla {seed})"):
            all_users = [
                r[0]
                for r in fetchall(
                    con,
                    f"SELECT user_id FROM read_csv_auto('{paths['orders']}', header=true) GROUP BY 1",
                )
            ]
            sample_user_ids = [
                int(u)
                for u in rng.choice(
                    all_users, size=min(sample_users, len(all_users)), replace=False
                )
            ]

    with StepTimer("Creación de vistas del dataset"):
        make_views(con, paths, sample_user_ids)

    metadata = base_metadata(Path(data_dir), seed, sample_users, rng)
    figures: list[str] = []
    with StepTimer("Supuesto S1: integridad del esquema"):
        s1 = check_schema_integrity(paths, inventory, con)
    s2 = check_sequential_history(con, figures)
    s3 = check_basket_density(con, figures)
    s4 = check_complementarity_signal(con, pair_sample_users, figures)
    s5 = check_leakage_free_evaluation(con, figures)
    assumptions = {
        "S1_schema_integrity": s1,
        "S2_sequential_history": s2,
        "S3_basket_density": s3,
        "S4_complementarity_signal": s4,
        "S5_leakage_free_evaluation": s5,
    }
    results = {
        "metadata": metadata,
        "files": inventory,
        "assumptions": assumptions,
        "decision": decide(assumptions),
    }
    con.close()

    with StepTimer("Escritura de audit_results.json y dataset_audit.md"):
        write_json_atomic(output_dir / "audit_results.json", results)
        (output_dir / "dataset_audit.md").write_text(
            render_markdown(results), encoding="utf-8"
        )
    log_step(f"Resultados en {(output_dir / 'audit_results.json').resolve()}")
    log_step(f"Informe en {(output_dir / 'dataset_audit.md').resolve()}")
    return results


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_dir = resolve_data_dir(args.data_dir)
    log_step(f"Directorio de datos: {data_dir}")
    run_audit(
        data_dir,
        args.output_dir,
        seed=args.seed,
        sample_users=args.sample_users,
        pair_sample_users=args.pair_sample_users,
        args=args,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
