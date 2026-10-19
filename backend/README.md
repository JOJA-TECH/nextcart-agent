# NEXTCART backend

Backend FastAPI del agente NEXTCART. Esta carpeta contiene todo el código Python, sus dependencias y sus pruebas.

## Contenido

- `src/backend.py`: aplicación FastAPI y endpoints.
- `src/schemas.py`: contratos Pydantic.
- `src/inference.py`: carga verificada del modelo y recomendación.
- `src/train_agent.py`: entrenamiento offline.
- `src/evaluate_agent.py`: evaluación offline y latencia.
- `src/audit_dataset.py`: auditoría S1–S5 del dataset.
- `src/catalog_db.py`: construcción y consulta del catálogo SQLite.
- `src/artifacts.py`: manifiesto y validación SHA-256.
- `src/storage.py`: almacenamiento JSON/JSONL y temporizadores.
- `tests/`: 44 pruebas backend y `tests/fixtures/mini_dataset/`.

## Instalación y pruebas

Ejecutar desde esta carpeta:

```bash
uv sync --extra dev
uv run pytest -q
```

## Arrancar la API

```bash
export NEXTCART_MODEL_PATH=../artifacts/nextcart_model.json
export NEXTCART_EVENTS_PATH=../logs/events.jsonl
uv run uvicorn src.backend:app --host 0.0.0.0 --port 8000
```

El backend usa por defecto:

- Modelo: `../artifacts/nextcart_model.json`.
- Manifiesto: junto al modelo.
- Catálogo: `../data/catalog.db`.
- Datos del catálogo: `../data/`.
- Eventos: `../logs/events.jsonl`.

Estas rutas también pueden cambiarse mediante variables de entorno. Consulta la tabla completa en el [README principal](../README.md#ejecución-rápida).

## Entrenamiento y evaluación

```bash
uv run python src/audit_dataset.py \
  --data-dir ../data --output-dir ../reports

uv run python src/train_agent.py \
  --data-dir ../data \
  --output ../artifacts/nextcart_model.json \
  --metrics-output ../reports/model_metrics.json

uv run python src/evaluate_agent.py \
  --data-dir ../data \
  --model ../artifacts/nextcart_model.json \
  --output ../reports/model_metrics.json
```

## Regla de arranque

El backend **no entrena**, **no descarga el dataset** y **no reconstruye reglas pesadas** cuando inicia. Solo carga el artefacto JSON, verifica su manifiesto y sirve la API. Si el modelo no existe o no pasa la validación, `/health` informa `model_loaded: false` y `/v1/recommendations` responde el error controlado correspondiente.

## Evidencias

- [Modelo](../artifacts/nextcart_model.json)
- [Manifiesto](../artifacts/artifact_manifest.json)
- [Métricas](../reports/model_metrics.json)
- [Auditoría](../reports/audit_results.json)
- [Eventos JSONL](../logs/events.jsonl)
- [Pruebas](tests/)
