# NEXTCART-AGENT

Agente de recomendación de productos complementarios (**next-basket
recommendation**) para una tienda en línea, entrenado y evaluado
**localmente** sobre el dataset Instacart. El proyecto cubre el flujo
completo: **auditoría del dataset (S1–S5) → entrenamiento local →
artefactos con manifiesto → backend FastAPI de inferencia**.

Modelo: baseline explicable y reproducible de **frecuencia global +
coocurrencia en cestas** (soporte, confianza, lift, recencia relativa,
boost de recompra, filtros de inventario/rechazo en inferencia). Sin LLM.

> ⚠️ El objetivo comercial de **≥ 12 % de aceptación en un A/B de dos
semanas** no puede validarse con Instacart: el dataset no contiene
impresiones, exposición, grupo control ni feedback de usuarios. Las
métricas de este proyecto son **offline** (predicción de cesta).

---

## 1. Qué hace el proyecto

| Etapa | Script | Qué produce |
| --- | --- | --- |
| Auditoría del dataset | `src/audit_dataset.py` | `reports/audit_results.json`, `reports/dataset_audit.md`, `reports/figures/*.png` |
| Entrenamiento | `src/train_agent.py` | `artifacts/nextcart_model.json`, `artifacts/artifact_manifest.json` |
| Evaluación offline | `src/evaluate_agent.py` | `reports/model_metrics.json`, `reports/figures/model_metrics_at_k.png` |
| Inferencia local | `src/inference.py` | Recomendaciones demo/CLI con el modelo ya entrenado (sin reentrenar) |
| Backend HTTP | `src/backend.py` | FastAPI con `/health`, `/v1/recommendations`, `/v1/catalog/*`, eventos y métricas |
| Catálogo SQLite | `src/catalog_db.py` | `data/catalog.db` (productos/pasillos/departamentos + precios demo deterministas) |
| Frontend de checkout | `frontend/` | React + Vite (pnpm) que consume el backend real; ver `frontend/README.md` |
| Notebook independiente | `notebooks/nextcart_audit_train.ipynb` | Auditoría S1–S5 (más S6/S7 adaptados del proyecto de referencia `old/`), entrenamiento y evaluación, autocontenido y didáctico; escribe en `notebooks/nb_out/` |

## 2. Todo se ejecuta en el equipo local

- No hay plataformas externas ni descargas automáticas. El dataset se lee
desde disco (por defecto `dataset/` o `data/`; configurable con
`--data-dir` o `NEXTCART_DATA_DIR`).

- Lectura por consultas con **DuckDB**, con límite de memoria configurable
(`--duckdb-memory-limit`) y volcado a disco (`--spill-dir`; evita `/tmp`
si es tmpfs). Los pares de coocurrencia se generan **por bloques** y se
escriben a parquet temporal para no materializar 150M+ de pares en RAM.

- Configurable: rutas, `--workers`, `--block-size`, muestreo opcional
(`--sample-users`, `--max-eval-users`; queda documentado en los
metadatos con método/semilla/motivo). La ejecución completa es el default.

- Cada paso imprime qué se está ejecutando y cuánto tarda (`StepTimer`).

- Si faltan archivos del dataset, el script aborta mostrando los que
faltan e instrucciones exactas de corrección. Nunca inventa resultados.

- Todos los resultados se escriben a disco y pueden revisarse después.

### Requisitos de recursos

| Recurso | Mínimo recomendado |
| --- | --- |
| RAM | 6–8 GB (DuckDB limitado a 2 GB por defecto) |
| Disco | ~1 GB libre en `reports/` y spill dir |
| CPU | 4+ núcleos útiles para evaluación paralela (`--workers`) |
| Python | ≥ 3.11 |

## 3. Instalación

```bash
uv sync --extra dev      # crea .venv, genera uv.lock e instala todo (pyproject.toml)
```

## 4. Flujo local completo (auditoría → entrenamiento → evaluación)

```bash
# En el equipo local, con el dataset Instacart en dataset/ (o data/)
python src/audit_dataset.py --data-dir dataset --output-dir reports
python src/train_agent.py --data-dir dataset \
    --output artifacts/nextcart_model.json \
    --metrics-output reports/model_metrics.json \
    --seed 42 --min-support 5 --top-k 100
python src/evaluate_agent.py --data-dir dataset \
    --model artifacts/nextcart_model.json --output reports/model_metrics.json
```

Con máquinas modestas, muestreo (queda registrado en los metadatos):

```bash
python src/audit_dataset.py --data-dir dataset --output-dir reports --sample-users 30000
python src/evaluate_agent.py --data-dir dataset --model artifacts/nextcart_model.json \
    --output reports/model_metrics.json --max-eval-users 20000 --workers 4
```

Cada script tiene `--help` con todos los parámetros.

## 5. Qué genera cada etapa

**Auditoría:** `reports/audit_results.json` (S1–S5 con métricas,
interpretación y limitaciones + decisión) y `reports/dataset_audit.md`
(informe del flujo con las figuras incrustadas).

**Entrenamiento:** `artifacts/nextcart_model.json` (versión, algoritmo,
parámetros, popular_products con recencia, association_rules
`[consecuente, count, confidence, lift]`, catálogo) y
`artifacts/artifact_manifest.json` (hash sha256, versiones, referencias).
Si el modelo no supera la validación pre-guardado se marca `experimental`,
nunca `candidate` (producción).

**Evaluación:** `reports/model_metrics.json` con Precision/Recall/HitRate/
MAP @K para K=1,3,5,10 de `topfreq`, `cooccur` y `nextcart_final`,
cobertura, repeat/explore, latencia offline, metodología del split
(oficial Instacart prior→train, sin fuga) y advertencias.

## 6. Backend y frontend: arranque para pruebas

Backend (FastAPI, con `uv`):

```bash
# bash / Linux / macOS
export NEXTCART_MODEL_PATH=artifacts/nextcart_model.json
uv run uvicorn src.backend:app --host 0.0.0.0 --port 8000
```

```
# Windows (PowerShell)
$env:NEXTCART_MODEL_PATH = "artifacts/nextcart_model.json"
uv run uvicorn src.backend:app --host 127.0.0.1 --port 8000
```

Frontend (React + Vite, con `pnpm`) en otra terminal:

```bash
cd frontend
pnpm install
pnpm dev    # http://localhost:5173
```

Por defecto el frontend llama por rutas relativas y el **proxy de Vite**
reenvía `/v1` y `/health` al backend (`http://localhost:8000`, configurable
con `NEXTCART_BACKEND_URL` ). Alternativa: llamar directo configurando
`VITE_NEXTCART_API_BASE_URL` en `frontend/.env` (ver `frontend/.env.example`);
el backend ya habilita CORS para los orígenes de Vite
(`localhost:5173/4173`). Detalles en `frontend/README.md`.

Reglas de arranque verificables en los tests: el backend **no entrena**, no
descarga el dataset, no ejecuta el flujo y no reconstruye reglas pesadas;
solo carga el artefacto JSON y verifica el manifiesto (existencia, versión,
hash). Sin modelo: `/health` responde `model_loaded: false` con instrucciones.

Variables de entorno:

| Variable | Uso |
| --- | --- |
| `NEXTCART_MODEL_PATH` | Ruta del artefacto del modelo (obligatoria para servir) |
| `NEXTCART_DATA_DIR` | Directorio de los CSV de Instacart para construir el catálogo (default `data/`) |
| `NEXTCART_CATALOG_DB_PATH` | Ruta de la BD SQLite del catálogo (default `data/catalog.db`; se construye sola si falta) |
| `NEXTCART_MANIFEST_PATH` | Ruta del manifiesto (opcional; por defecto junto al modelo) |
| `NEXTCART_ADMIN_TOKEN` | Habilita y protege `POST /v1/admin/reload-model` |
| `NEXTCART_EVENTS_PATH` | Ruta del log de eventos (default `logs/events.jsonl`) |
| `NEXTCART_CORS_ORIGINS` | Orígenes CORS permitidos, separados por comas (default: Vite en `localhost:5173`/`4173`) |

## 7. Probar los endpoints con curl

```bash
# salud
curl -s localhost:8000/health

# recomendaciones (inventario con claves string, k entre 1 y 10)
curl -s -X POST localhost:8000/v1/recommendations \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"sess-001","cart":[24852,13176],
       "navigation":[{"type":"view","product_id":47209}],
       "recent_history":[[24852,13176],[47209]],
       "rejected":[22935],
       "inventory":{"21137":true,"22935":false},
       "k":3}'

# impresión de las recomendaciones mostradas
curl -s -X POST localhost:8000/v1/events/impression \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"sess-001","recommendation_ids":[21137,47209],
       "cart":[24852,13176],"model_version":"2000000.1"}'

# feedback (accepted | rejected | ignored)
curl -s -X POST localhost:8000/v1/events/feedback \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"sess-001","product_id":21137,"event":"accepted",
       "recommendation_ids":[21137,47209]}'# métricas observadas

curl -s localhost:8000/v1/metrics/summary

# catálogo del dataset (SQLite, precios demo deterministas COP)

curl -s "localhost:8000/v1/catalog/products?search=banana&department_id=4&limit=3"

curl -s localhost:8000/v1/catalog/products/24852

curl -s localhost:8000/v1/catalog/departments

# recarga del modelo ya entrenado (opcional, protegido)
export NEXTCART_ADMIN_TOKEN=dev-token
curl -s -X POST localhost:8000/v1/admin/reload-model \
  -H 'X-Admin-Token: dev-token'
```

## 8. Qué métricas son offline y qué no

**Offline (medibles aquí con el dataset):** Precision@K, Recall@K,
HitRate@K, MAP@K sobre el split oficial prior→train, cobertura del
catálogo, composición repeat/explore de los aciertos y latencia de
inferencia.

**Solo con usuarios reales (A/B de dos semanas en producción):** la tasa de
aceptación y el objetivo de ≥ 12 %. Instacart no tiene impresiones,
posición del widget, grupo de control, ni eventos de aceptación — incluidos
aquí unicamente como registro de eventos del backend.

## 9. Por qué el 12 % necesita A/B real

No existe señal supervisada de aceptación en el dataset. La aceptación
depende de factores ajenos al histórico de compras: exposición real del
widget, inventario y precios vigentes, y comportamiento del usuario frente
al control. Un A/B (grupo tratamiento vs control, ventana de dos semanas,
definición de usuario expuesto) es el único diseño causal que puede medir
el 12 % de aceptación; `Recall@K` offline no es conversión comercial y el
backend lo advierte en `/v1/metrics/summary`.

## 10. Limitaciones del dataset Instacart

- **Inventario:** no hay stock real; el filtro de agotados solo se puede
aplicar en tiempo de inferencia con datos en vivo de la tienda.

- **Precio:** sin precios ni promociones; no se puede optimizar margen. El
catálogo HTTP sí sirve **precios de demostración deterministas** en COP
(`mismo product_id ⇒ mismo precio`; hash con semilla fija) para la
interfaz, marcados como demo; no son precios reales.

- **Posición del widget:** sin impresiones ni posición; no hay señal de
exposición ni de vertical-bias.

- **Aceptación:** sin feedback de usuarios; la métrica comercial solo con A/B.

- **Tiempo:** sin timestamps absolutos (solo `order_number`, `order_dow`,
`order_hour_of_day`, `days_since_prior_order`); la recencia es relativa.

## 11. Estructura del proyecto

```
nextcart-agent/
├── README.md
├── pyproject.toml          # dependencias del proyecto (uv genera uv.lock)
├── data/README.md          # dónde dejar los CSV del dataset Instacart
├── src/
│   ├── config.py        # rutas, defaults, semilla
│   ├── schemas.py       # contratos Pydantic (validaciones)
│   ├── catalog_db.py    # catálogo SQLite del dataset + precios demo deterministas
│   ├── audit_dataset.py # auditoría S1–S5 con DuckDB + figuras + informe
│   ├── train_agent.py   # modelo coocurrencia+frecuencia; manifiesto
│   ├── evaluate_agent.py# offline eval @K, cobertura, repeat/explore, latencia
│   ├── inference.py     # carga del artefacto (sin reentrenar) + CLI demo
│   ├── artifacts.py     # validación/verificación de artefacto y manifiesto
│   ├── storage.py       # JSON atómico, JSONL, hash, timers
│   └── backend.py       # FastAPI: /health, /v1/*, eventos, métricas y CORS
├── tests/               # fixtures mini_dataset + 44 tests (sin red)
├── frontend/            # React + Vite + Chakra (pnpm); ver frontend/README.md
├── notebooks/nextcart_audit_train.ipynb  # notebook independiente
├── reports/             # audit_results.json, dataset_audit.md,
│                        # model_metrics.json, figures/*  (ver README)
├── artifacts/           # nextcart_model.json + manifest (ver README)
└── logs/events.jsonl    # eventos del backend (se crea al correr)
```

## 12. Flujo resumido (lo que explica este README)

`auditoría local` → `entrenamiento local` → `artefactos + manifiesto`
→ `backend` (solo carga y sirve, nunca entrena). Los tests livianos
(`pytest -q`, 44 tests, segundos) cubren esquemas, inferencia, contratos
HTTP y pipeline completo sobre un fixture pequeño. El frontend además
tiene una suite E2E con Playwright (`frontend/e2e`, `pnpm test:e2e`) que
corre contra el backend real; CI en `.github/workflows/ci.yml`.
