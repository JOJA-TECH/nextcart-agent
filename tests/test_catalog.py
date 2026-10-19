"""Tests del catálogo SQLite: construcción, precios deterministas y endpoints."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.backend import create_app
from src.catalog_db import (
    build_catalog_db,
    demo_price_for_product,
    ensure_catalog_db,
    get_product,
    list_aisles,
    list_departments,
    list_products,
    open_catalog_db,
)

PRODUCTS_CSV = """product_id,product_name,aisle_id,department_id
1,Chocolate Sandwich Cookies,61,19
2,All-Seasons Salt,104,13
3,Banana Orgánica,9,1
4,Fresa Colosal,9,1
5,Leche Entera,2,16
"""

AISLES_CSV = """aisle_id,aisle
9,fruits
2,dairy
61,cookies cakes
104,spices seasonings
"""

DEPARTMENTS_CSV = """department_id,department
1,produce
13,pantry
16,dairy eggs
19,snacks
"""


def _write_dataset(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "products.csv").write_text(PRODUCTS_CSV, encoding="utf-8")
    (data_dir / "aisles.csv").write_text(AISLES_CSV, encoding="utf-8")
    (data_dir / "departments.csv").write_text(DEPARTMENTS_CSV, encoding="utf-8")
    return data_dir


@pytest.fixture()
def mini_data_dir(tmp_path: Path) -> Path:
    return _write_dataset(tmp_path / "data")


def _catalog_app(
    tmp_path: Path, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    # El entorno puede tener NEXTCART_MODEL_PATH/NEXTCART_DATA_DIR definidos;
    # los tests son independientes del equipo.
    for var in ("NEXTCART_MODEL_PATH", "NEXTCART_DATA_DIR"):
        monkeypatch.delenv(var, raising=False)
    app = create_app(
        model_path=None,
        events_path=tmp_path / "events.jsonl",
        catalog_db_path=tmp_path / "catalog.db",
        catalog_data_dir=data_dir,
    )
    return TestClient(app)


def test_demo_price_is_deterministic_per_product():
    # "Random" pero reproducible: mismo producto ⇒ mismo precio siempre.
    assert demo_price_for_product(24852) == demo_price_for_product(24852)
    assert demo_price_for_product(24852, seed="k") == demo_price_for_product(
        24852, seed="k"
    )
    # Otra semilla ⇒ otra serie de precios reproducible.
    assert demo_price_for_product(24852) != demo_price_for_product(24852, seed="otra")
    low, high = demo_price_for_product(1), demo_price_for_product(50_000)
    assert 1_000 <= low <= 45_000
    assert 1_000 <= high <= 45_000
    assert low % 50 == 0


def test_build_catalog_from_csvs(mini_data_dir: Path, tmp_path: Path):
    db = tmp_path / "catalog.db"
    summary = build_catalog_db(mini_data_dir, db)
    assert summary["products"] == 5
    assert summary["aisles"] == 4
    assert summary["departments"] == 4
    assert db.is_file()
    # idempotente: reconstruir da la misma BD (mismos precios)
    prices = demo_price_for_product(3)
    build_catalog_db(mini_data_dir, db, overwrite=True)
    conn = open_catalog_db(db)
    assert get_product(conn, 3)["price"] == prices
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_build_requires_missing_csvs_with_clear_error(tmp_path: Path):
    empty = tmp_path / "vacio"
    empty.mkdir()
    with pytest.raises(Exception, match="Falta el archivo del dataset"):
        build_catalog_db(empty, tmp_path / "catalog.db")


def test_list_products_filters_search_and_pagination(mini_data_dir: Path, tmp_path: Path):
    conn = ensure_catalog_db(tmp_path / "catalog.db", mini_data_dir)
    page1 = list_products(conn, limit=2, offset=0)
    assert page1["total"] == 5
    assert len(page1["items"]) == 2

    page2 = list_products(conn, limit=2, offset=2)
    assert page2["items"][0]["product_id"] != page1["items"][0]["product_id"]

    banana = list_products(conn, search="orgánica")
    assert banana["items"] and banana["items"][0]["product_id"] == 3

    by_dept = list_products(conn, department_id=1)
    assert all(p["department_id"] == 1 for p in by_dept["items"])

    by_aisle = list_products(conn, aisle_id=2)
    assert [p["product_id"] for p in by_aisle["items"]] == [5]

    # cada producto conserva su precio (determinista) y metadatos del dataset
    prod = get_product(conn, 1)
    assert prod["product_name"] == "Chocolate Sandwich Cookies"
    assert prod["aisle"] == "cookies cakes"
    assert prod["department"] == "snacks"
    assert prod["price"] == demo_price_for_product(1)

    assert list_departments(conn)[0]["product_count"] >= 0
    aisles = list_aisles(conn, department_id=1)
    assert {a["aisle"] for a in aisles} == {"fruits"}
    conn.close()


def test_open_catalog_rejects_invalid_db(tmp_path: Path):
    bad = tmp_path / "no-catalogo.db"
    conn = sqlite3.connect(bad)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()
    with pytest.raises(Exception, match="no es un catálogo válido"):
        open_catalog_db(bad)


def test_catalog_endpoints(
    mini_data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _catalog_app(tmp_path, mini_data_dir, monkeypatch)
    with client:
        health = client.get("/health").json()
        assert health["catalog_loaded"] is True

        products = client.get("/v1/catalog/products", params={"limit": 3})
        assert products.status_code == 200
        body = products.json()
        assert body["total"] == 5 and len(body["items"]) == 3
        item = body["items"][0]
        assert set(item) >= {
            "product_id", "product_name", "aisle_id", "department_id",
            "price", "currency", "aisle", "department",
        }
        assert item["currency"] == "COP"

        search = client.get("/v1/catalog/products", params={"search": "fresa"}).json()
        assert [p["product_id"] for p in search["items"]] == [4]
        # búsqueda insensible a mayúsculas/minúsculas (LIKE)
        assert (
            client.get("/v1/catalog/products", params={"search": "FRESA"}).json()
            == search
        )

        filtered = client.get(
            "/v1/catalog/products", params={"department_id": 1}
        ).json()
        assert all(p["department_id"] == 1 for p in filtered["items"])

        by_id = client.get("/v1/catalog/products/3")
        assert by_id.status_code == 200
        assert by_id.json()["product_name"] == "Banana Orgánica"
        assert by_id.json()["price"] == demo_price_for_product(3)

        assert (
            client.get("/v1/catalog/products/9999999").status_code == 404
        )
        assert (
            client.get("/v1/catalog/products", params={"limit": 0}).status_code == 422
        )
        assert (
            client.get(
                "/v1/catalog/products", params={"limit": 101}
            ).status_code == 422
        )

        departments = client.get("/v1/catalog/departments").json()
        assert {d["department"] for d in departments["items"]} >= {
            "produce", "snacks",
        }
        assert all(
            d["department"].casefold() == d["department"].casefold()
            for d in departments["items"]
        )
        aisles = client.get("/v1/catalog/aisles", params={"department_id": 1}).json()
        assert {a["aisle"] for a in aisles["items"]} == {"fruits"}


def test_catalog_endpoints_503_without_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    empty = tmp_path / "vacio"
    empty.mkdir()
    client = _catalog_app(tmp_path, empty, monkeypatch)
    with client:
        health = client.get("/health").json()
        assert health["catalog_loaded"] is False
        for path in ("/v1/catalog/products", "/v1/catalog/departments",
                     "/v1/catalog/aisles", "/v1/catalog/products/1"):
            r = client.get(path)
            assert r.status_code == 503, path
            assert r.json()["detail"]["error"] == "catalog_unavailable"
