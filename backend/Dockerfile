# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/backend/.venv/bin:$PATH" \
    PORT=8000 \
    NEXTCART_MODEL_PATH=/app/artifacts/nextcart_model.json \
    NEXTCART_MANIFEST_PATH=/app/artifacts/artifact_manifest.json \
    NEXTCART_DATA_DIR=/app/data \
    NEXTCART_CATALOG_DB_PATH=/app/data/catalog.db \
    NEXTCART_EVENTS_PATH=/app/logs/events.jsonl

WORKDIR /app

# uv instala exactamente las versiones fijadas en backend/uv.lock.
COPY backend/pyproject.toml backend/uv.lock /app/backend/
RUN pip install --no-cache-dir uv \
    && uv sync --directory /app/backend --frozen --no-dev --no-install-project \
    && pip uninstall -y uv \
    && rm -rf /root/.cache

# El backend necesita el código y los artefactos compartidos del repositorio.
COPY backend/src /app/backend/src
COPY artifacts /app/artifacts
COPY data /app/data

# Los eventos deben sobrevivir al reinicio si Coolify monta /app/logs como volumen.
RUN mkdir -p /app/logs \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin nextcart \
    && chown -R nextcart:nextcart /app

USER nextcart
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=3)" || exit 1

CMD ["sh", "-c", "exec uvicorn src.backend:app --host 0.0.0.0 --port ${PORT:-8000}"]
