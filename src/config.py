"""Configuración central: rutas, constantes del dataset y valores por defecto."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATASET_FILES = {
    "orders": "orders.csv",
    "order_products_prior": "order_products__prior.csv",
    "order_products_train": "order_products__train.csv",
    "products": "products.csv",
    "aisles": "aisles.csv",
    "departments": "departments.csv",
}

REQUIRED_COLUMNS = {
    "orders": [
        "order_id",
        "user_id",
        "eval_set",
        "order_number",
        "order_dow",
        "order_hour_of_day",
        "days_since_prior_order",
    ],
    "order_products_prior": [
        "order_id",
        "product_id",
        "add_to_cart_order",
        "reordered",
    ],
    "order_products_train": [
        "order_id",
        "product_id",
        "add_to_cart_order",
        "reordered",
    ],
    "products": ["product_id", "product_name", "aisle_id", "department_id"],
    "aisles": ["aisle_id", "aisle"],
    "departments": ["department_id", "department"],
}

MODEL_ALGORITHM = "cooccurrence_frequency"
MODEL_FORMAT_VERSION = 1
MODEL_STATUS_CANDIDATE = "candidate"
MODEL_STATUS_EXPERIMENTAL = "experimental"

EVENT_LOG_APPEND = "append"
DISCLAIMER_AB_TEST = (
    "Estas métricas no constituyen evidencia de un A/B comercial si no existe "
    "asignación de control/tratamiento, definición de usuario expuesto y ventana "
    "de medición."
)


@dataclass
class Defaults:
    seed: int = 42
    min_support: int = 5
    top_k_rules: int = 100
    max_antecedents: int = 20000
    top_popular: int = 1000
    block_size: int = 100000
    history_items_used: int = 50
    pop_weight: float = 0.15
    repeat_boost: float = 0.25
    nav_weight: float = 0.5
    rejection_penalty: float = 0.2
    lift_cap: float = 5.0
    eval_ks: tuple[int, ...] = (1, 3, 5, 10)
    workers: int = field(default_factory=lambda: min(4, os.cpu_count() or 1))
    duckdb_memory_limit: str = "2GB"
    duckdb_spill_dir: str = "/tmp/opencode/duckdb_spill"


DEFAULTS = Defaults()


def resolve_data_dir(cli_value: str | Path | None = None) -> Path:
    """Resuelve el directorio del dataset.

    Orden de precedencia: argumento CLI, variable de entorno NEXTCART_DATA_DIR,
    `dataset/` (ubicación real en esta máquina), `data/` (alternativa documentada).
    No se inventan archivos: si no existen CSV, el error lo lanzará el script que
    los solicite.
    """
    if cli_value is not None:
        return Path(cli_value).expanduser().resolve()
    env = os.environ.get("NEXTCART_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    for candidate in (PROJECT_ROOT / "dataset", PROJECT_ROOT / "data"):
        if (candidate / DATASET_FILES["orders"]).is_file():
            return candidate.resolve()
    return (PROJECT_ROOT / "dataset").resolve()


def dataset_file(data_dir: Path, key: str) -> Path:
    return Path(data_dir) / DATASET_FILES[key]
