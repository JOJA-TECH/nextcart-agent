r"""Catálogo de productos NEXTCART en SQLite.

Genera y consulta una base de datos liviana (``data/catalog.db`` por
defecto) con los productos, pasillos y departamentos del dataset Instacart
(los CSV en ``data/`` o ``dataset/``) para servirlos al frontend por HTTP.

Reglas del proyecto (verificadas en tests):
- Nada de red: la BD se construye leyendo los CSV desde disco.
- Precios de demostración: el dataset Instacart no incluye precios, así que
  se asigna un precio determinista por producto (mismo product_id ⇒ mismo
  precio siempre, independiente de cuántas veces se reconstruya la BD).
  Se marca en la tabla ``metadata`` como precio de demostración COP.

Uso del backend: ``ensure_catalog_db()`` construye la BD si falta y devuelve
una conexión de solo lectura para los endpoints ``/v1/catalog/*``. La
construcción es liviana (solo products/aisles/departments.csv, ~2.5 MB);
nunca lee orders.csv ni order_products\*.csv.

CLI::

    python -m src.catalog_db build --data-dir data --db-path data/catalog.db
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any

# Semilla por defecto para los precios de demostración. Cambiarla cambia los
# precios de TODA la BD de forma reproducible.
DEFAULT_PRICE_SEED = "nextcart-demo-prices-v1"
DEFAULT_CURRENCY = "COP"
# Rango de precios (COP) y redondeo a centenas de 50.
PRICE_LOW = 1_000
PRICE_HIGH = 45_000
PRICE_ROUND_TO = 50

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS departments (
    department_id INTEGER PRIMARY KEY,
    department TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aisles (
    aisle_id INTEGER PRIMARY KEY,
    aisle TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    aisle_id INTEGER NOT NULL REFERENCES aisles(aisle_id),
    department_id INTEGER NOT NULL REFERENCES departments(department_id),
    price INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_products_aisle ON products(aisle_id);
CREATE INDEX IF NOT EXISTS idx_products_department ON products(department_id);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);
"""


class CatalogError(RuntimeError):
    """Error al construir o abrir la BD del catálogo."""


def demo_price_for_product(
    product_id: int,
    seed: str = DEFAULT_PRICE_SEED,
    low: int = PRICE_LOW,
    high: int = PRICE_HIGH,
    round_to: int = PRICE_ROUND_TO,
) -> int:
    """Precio determinista de demostración para un producto (COP).

    Mismo ``product_id`` ⇒ mismo precio, siempre (hash con semilla fija). El
    dataset Instacart no trae precios: esto es un valor de presentación.
    """
    if high <= low or round_to <= 0:
        raise ValueError("rango de precio inválido")
    digest = hashlib.blake2b(
        f"{seed}:{product_id}".encode("utf-8"), digest_size=8
    ).digest()
    value = int.from_bytes(digest, "big") % (high - low + 1)
    return low + (value // round_to) * round_to


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Lee un CSV y devuelve (encabezados, filas). Aborta si falta el archivo."""
    if not path.is_file():
        raise CatalogError(
            f"Falta el archivo del dataset: {path}. "
            f"Coloca los CSV de Instacart en ese directorio "
            f"(products.csv, aisles.csv, departments.csv) y reintenta."
        )
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = [row for row in reader if any((v or "").strip() for v in row.values())]
    return columns, rows


def _require_columns(columns: list[str], required: set[str], path: Path) -> None:
    missing = required - set(columns)
    if missing:
        raise CatalogError(
            f"El archivo {path.name} no tiene las columnas esperadas "
            f"(faltan: {sorted(missing)})."
        )


def build_catalog_db(
    data_dir: Path | str,
    db_path: Path | str,
    price_seed: str = DEFAULT_PRICE_SEED,
    overwrite: bool = False,
    currency: str = DEFAULT_CURRENCY,
) -> dict[str, Any]:
    """Construye la BD SQLite del catálogo desde los CSV del dataset.

    Devuelve un resumen (conteos, semilla, rutas). Reconstruible: los
    recompra se repiten exactamente con la misma semilla.
    """
    data_dir = Path(data_dir)
    db_path = Path(db_path)
    if db_path.exists():
        if not overwrite:
            raise CatalogError(
                f"La BD del catálogo ya existe: {db_path} (usa overwrite=True)."
            )
        db_path.unlink()

    products_path = data_dir / "products.csv"
    aisles_path = data_dir / "aisles.csv"
    departments_path = data_dir / "departments.csv"

    p_cols, product_rows = _read_csv(products_path)
    _require_columns(
        p_cols,
        {"product_id", "product_name", "aisle_id", "department_id"},
        products_path,
    )
    a_cols, aisle_rows = _read_csv(aisles_path)
    _require_columns(a_cols, {"aisle_id", "aisle"}, aisles_path)
    d_cols, dept_rows = _read_csv(departments_path)
    _require_columns(d_cols, {"department_id", "department"}, departments_path)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_name(db_path.name + ".tmp")
    conn = sqlite3.connect(tmp_path)
    try:
        conn.executescript(_SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO departments (department_id, department) VALUES (?, ?)",
            [
                (int(row["department_id"]), row["department"].strip())
                for row in dept_rows
                if (row.get("department_id") or "").strip()
            ],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO aisles (aisle_id, aisle) VALUES (?, ?)",
            [
                (int(row["aisle_id"]), row["aisle"].strip())
                for row in aisle_rows
                if (row.get("aisle_id") or "").strip()
            ],
        )
        prices = {
            row["product_id"]: demo_price_for_product(
                int(row["product_id"]), price_seed
            )
            for row in product_rows
        }
        conn.executemany(
            "INSERT OR REPLACE INTO products "
            "(product_id, product_name, aisle_id, department_id, price) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    int(row["product_id"]),
                    row["product_name"].strip(),
                    int(row["aisle_id"]),
                    int(row["department_id"]),
                    price,
                )
                for row in product_rows
                if (row.get("product_id") or "").strip()
                for price in (prices[row["product_id"]],)
            ],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            [
                ("schema_version", str(SCHEMA_VERSION)),
                ("price_seed", price_seed),
                ("currency", currency),
                ("price_low", str(PRICE_LOW)),
                ("price_high", str(PRICE_HIGH)),
                ("price_kind", "demo-deterministic"),
                ("source", str(data_dir)),
            ],
        )
        conn.commit()
        summary = {
            "departments": conn.execute("SELECT COUNT(*) FROM departments").fetchone()[
                0
            ],
            "aisles": conn.execute("SELECT COUNT(*) FROM aisles").fetchone()[0],
            "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "price_seed": price_seed,
            "currency": currency,
            "data_dir": str(data_dir),
            "db_path": str(db_path),
        }
    finally:
        conn.close()
    os.replace(tmp_path, db_path)
    return summary


def open_catalog_db(db_path: Path | str) -> sqlite3.Connection:
    """Abre la BD del catálogo (read-only) y valida el esquema mínimo."""
    path = Path(db_path)
    if not path.is_file():
        raise CatalogError(f"No existe la BD del catálogo: {path}.")
    # immutable=0 pero URI read-only evita escrituras accidentales del backend.
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        has_products = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
        ).fetchone()
        if has_products is None:
            raise CatalogError(f"La BD {path} no es un catálogo válido.")
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            raise CatalogError(f"La BD {path} está vacía.")
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise CatalogError(f"La BD {path} no es válida: {exc}") from exc
    return conn


def ensure_catalog_db(
    db_path: Path | str,
    data_dir: Path | str,
    price_seed: str = DEFAULT_PRICE_SEED,
) -> sqlite3.Connection:
    """Abre el catálogo; lo construye si falta. Lanza CatalogError si no puede."""
    db_path = Path(db_path)
    if not db_path.is_file():
        build_catalog_db(Path(data_dir), db_path, price_seed=price_seed)
    return open_catalog_db(db_path)


# ---------------------------------------------------------------------------
# Consultas (conexiones inmutables de ensure_catalog_db / open_catalog_db)
# ---------------------------------------------------------------------------


def get_product(conn: sqlite3.Connection, product_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT p.product_id, p.product_name, p.aisle_id, p.department_id, p.price,
               a.aisle AS aisle, d.department AS department
        FROM products p
        LEFT JOIN aisles a ON a.aisle_id = p.aisle_id
        LEFT JOIN departments d ON d.department_id = p.department_id
        WHERE p.product_id = ?
        """,
        (product_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def list_products(
    conn: sqlite3.Connection,
    *,
    search: str | None = None,
    department_id: int | None = None,
    aisle_id: int | None = None,
    limit: int = 24,
    offset: int = 0,
) -> dict[str, Any]:
    """Lista con paginación y filtros; devuelve total + items."""
    where: list[str] = []
    params: list[Any] = []
    if search:
        where.append("p.product_name LIKE ? ESCAPE '\\'")
        like = (
            search.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        )
        params.append(f"%{like}%")
    if department_id is not None:
        where.append("p.department_id = ?")
        params.append(department_id)
    if aisle_id is not None:
        where.append("p.aisle_id = ?")
        params.append(aisle_id)
    where_sql = f" WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(
        "SELECT COUNT(*) FROM products p" + where_sql, params
    ).fetchone()[0]
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    rows = conn.execute(
        """
        SELECT p.product_id, p.product_name, p.aisle_id, p.department_id, p.price,
               a.aisle AS aisle, d.department AS department
        FROM products p
        LEFT JOIN aisles a ON a.aisle_id = p.aisle_id
        LEFT JOIN departments d ON d.department_id = p.department_id
        """
        + where_sql
        + " ORDER BY p.product_name COLLATE NOCASE, p.product_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    items = [dict(row) for row in rows]
    return {"total": total, "limit": limit, "offset": offset, "items": items}


def list_departments(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT d.department_id, d.department,
               COUNT(p.product_id) AS product_count
        FROM departments d
        LEFT JOIN products p ON p.department_id = d.department_id
        GROUP BY d.department_id, d.department
        ORDER BY d.department COLLATE NOCASE
        """
    ).fetchall()
    return [dict(row) for row in rows]


def list_aisles(
    conn: sqlite3.Connection, department_id: int | None = None
) -> list[dict[str, Any]]:
    """Pasillos con su departamento (derivado de products, como en Instacart)
    y conteo de productos."""
    # En Instacart la relación aisle→department vive en products.csv; se
    # deriva con una agregación por pasillo.
    sql = """
        SELECT x.aisle_id, a.aisle,
               x.department_id AS department_id,
               COUNT(p.product_id) AS product_count
        FROM (
            SELECT pm.aisle_id, MIN(pm.department_id) AS department_id
            FROM products pm
            GROUP BY pm.aisle_id
        ) AS x
        JOIN aisles a ON a.aisle_id = x.aisle_id
        LEFT JOIN products p ON p.aisle_id = x.aisle_id
        {dept}
        GROUP BY x.aisle_id, a.aisle, x.department_id
        ORDER BY a.aisle COLLATE NOCASE
    """.format(dept="WHERE x.department_id = ?" if department_id is not None else "")
    rows = conn.execute(
        sql, tuple() if department_id is None else (department_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def catalog_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "aisles": conn.execute("SELECT COUNT(*) FROM aisles").fetchone()[0],
        "departments": conn.execute("SELECT COUNT(*) FROM departments").fetchone()[0],
        "currency": "COP",
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BD SQLite del catálogo NEXTCART")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="construir/actualizar data/catalog.db")
    build.add_argument("--data-dir", default="data")
    build.add_argument("--db-path", default="data/catalog.db")
    build.add_argument("--price-seed", default=DEFAULT_PRICE_SEED)
    args = parser.parse_args(argv)
    if args.command == "build":
        db_path = Path(args.db_path)
        if not db_path.is_file():
            summary = build_catalog_db(
                args.data_dir, db_path, price_seed=args.price_seed
            )
        else:
            # Reconstrucción idempotente: mismos datos ⇒ misma BD.
            summary = build_catalog_db(
                args.data_dir, db_path, price_seed=args.price_seed, overwrite=True
            )
        print(
            f"[catalog] BD construida en {summary['db_path']}: "
            f"{summary['products']} productos, {summary['aisles']} pasillos, "
            f"{summary['departments']} departamentos (precios demo: {summary['currency']}, "
            f"semilla {summary['price_seed']})."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
