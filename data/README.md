# data/ — dataset Instacart (opcional)

Este proyecto lee el dataset **Instacart Online Grocery Basket Analysis**
desde disco, sin descargas automáticas.

En esta máquina los CSV viven en `dataset/` (ubicación autodetectada).
Si prefieres usar `data/`, coloca aquí los seis archivos:

```
data/
├── orders.csv
├── order_products__prior.csv
├── order_products__train.csv
├── products.csv
├── aisles.csv
└── departments.csv
```

Descarga (manual): https://www.kaggle.com/datasets/yasserh/instacart-online-grocery-basket-analysis-dataset

Cambiar la ubicación:

```bash
export NEXTCART_DATA_DIR=/ruta/a/data      # o
python src/audit_dataset.py --data-dir data --output-dir reports
```

Tamaños aproximados del dataset completo (referencia):

| Archivo | Tamaño | Filas |
|---|---:|---:|
| order_products__prior.csv | ~551 MB | 32.4 M |
| orders.csv | ~104 MB | 3.4 M |
| order_products__train.csv | ~24 MB | 1.4 M |
| products.csv | ~2 MB | 50 k |
| aisles.csv / departments.csv | ~4 KB | 134 / 21 |

Requisito de recursos: ≥ 6 GB RAM para auditoría/entrenamiento con DuckDB
(con límite configurable `--duckdb-memory-limit` y volcado a disco en
`--spill-dir`; evita `/tmp` si es tmpfs).
