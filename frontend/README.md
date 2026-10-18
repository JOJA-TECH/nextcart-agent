# NEXTCART frontend (React + Vite) — Backend real únicamente

Frontend de checkout con recomendaciones que consume **exclusivamente** el backend FastAPI existente del repositorio. No incluye modo Prototype, datos mock, cliente mock ni simulación local: si el backend está apagado, la interfaz muestra un error de conexión.

## Puesta en marcha

```bash
# Backend, desde la raíz del repositorio (usa uv)
uv sync --extra dev

# bash / Linux / macOS
export NEXTCART_MODEL_PATH=artifacts/nextcart_model.json
uv run uvicorn src.backend:app --host 0.0.0.0 --port 8000
```

```powershell
# Windows (PowerShell)
$env:NEXTCART_MODEL_PATH = "artifacts/nextcart_model.json"
uv run uvicorn src.backend:app --host 127.0.0.1 --port 8000
```

```bash
# Frontend, en otra terminal
cd frontend
pnpm install
pnpm dev    # http://localhost:5173
```

La URL del backend se resuelve así:

- **Por defecto (sin `.env`):** rutas relativas → el **proxy de Vite**
  (`vite.config.ts`) reenvía `/v1` y `/health` a `http://localhost:8000`
  (destino configurable con `NEXTCART_BACKEND_URL`).
- **URL directa:** copia `.env.example` a `.env` y define
  `VITE_NEXTCART_API_BASE_URL=http://localhost:8000` (o déjala vacía para
  volver al proxy). Requiere CORS, que ya está habilitado en el backend.

## Endpoints consumidos (único modo de ejecución)

- `GET /health`
- `POST /v1/recommendations`
- `POST /v1/events/impression`
- `POST /v1/events/feedback`
- `GET /v1/metrics/summary`

No se usa `/v1/admin/reload-model` (requiere token administrativo y no es operación de usuario).

## Datos reales vs. datos de presentación

- **Reales del backend**: los IDs numéricos del dataset Instacart (por ejemplo `24852`, `13176`, `21137`), `score`, `reason`, `source`, `fallback`, `warnings`, `model_version`, `latency_ms` y las métricas de `/v1/metrics/summary`.
- **De presentación (`catálogo-demo`)**: nombres, precios, categorías e imágenes. Viven en `src/shared/catalog-demo.ts` y están marcados con la etiqueta `catálogo-demo` en la interfaz. No provienen del dataset Instacart ni del modelo.

## Nota sobre IA

El backend actual no expone un endpoint de explicación con IA. El frontend **no** llama a ningún LLM, no usa `VITE_OPENAI_API_KEY` ni claves secretas, y no genera contenido de IA. Solo existe la interfaz futura `ExplanationService` (sin implementación) en `src/shared/ai/no-ai.ts`, y la nota visible: «IA no integrada en el backend actual — NEXTCART funciona con el modelo local sin LLM». Cualquier integración futura debe agregarse primero al backend Python.

## CORS y proxy

Cubierto por las dos vías:

- **Proxy de desarrollo (por defecto):** sin `.env`, `vite.config.ts`
  reenvía `/v1` y `/health` al backend; el navegador nunca cruza orígenes.
- **CORS en el backend:** `src/backend.py` incluye `CORSMiddleware` que
  acepta los orígenes de Vite (`http://localhost:5173` y
  `http://127.0.0.1:5173`, más `:4173` para `pnpm preview`). Útil cuando se
  usa `VITE_NEXTCART_API_BASE_URL` con la URL directa del backend.

## Verificación de conexión (2026-10-18)

Probado end-to-end contra el backend real (`artifacts/nextcart_model.json`,
Python 3.14 + uv, Node 24 + pnpm): `/health` con modelo cargado,
`POST /v1/recommendations` con respuestas del modelo, ciclo
impresión → feedback → `/v1/metrics/summary` actualizando contadores, todo a
través del proxy de `pnpm dev`, y con CORS verificado por URL directa.
`pnpm build` compila sin errores (incluida la resolución del alias `@/` en
Windows).

## Pruebas T01–T12

Las pruebas se ejecutan **manualmente contra el backend real** desde el panel «Diagnóstico y guía T01–T12» de la interfaz. No se usan MSW ni mocks de red en la aplicación. Las pruebas automatizadas quedan pendientes y, cuando se agreguen, deben ejecutarse contra un backend de prueba real o un entorno de integración controlado.

Pruebas ejecutadas realmente en esta entrega (verificación visual contra respuestas HTTP reales, con un servidor que hablaba el contrato real de los endpoints):

- T01 — Recomendación normal: tarjetas con IDs numéricos, `score`, `reason` y `source` del backend.
- T02 — Aceptación: evento `accepted` con HTTP 202 y confirmación visible solo tras la respuesta.
- T03 — Rechazo: evento `rejected` con HTTP 202 y etiqueta «rechazado» solo tras la respuesta.
- T04 — No repetición: los IDs rechazados persisten en la sesión y la pantalla se mantiene estable al re-solicitar.
- T07 — Backend degradado: badge «Backend degradado» con `model_loaded: false` y HTTP 503 con mensaje de error y reintento.
- T08 — Solicitud inválida: HTTP 422 mostrado de forma legible con la pantalla estable.
- T09 — Carrito vacío: `cart: []` real, `fallback: true` y advertencias del backend visibles.
- T10/T11/T12 — Validados en su parte de interfaz (inventario deshabilitado, nota de ausencia de IA, manejo de 401/403 en el cliente).
- Backend apagado: la interfaz muestra «Backend no disponible» y el error de conexión sin datos simulados.
- Compilación de producción y verificación en escritorio y móvil.

Pruebas pendientes (requieren el backend FastAPI real levantado con el modelo `artifacts/nextcart_model.json`): T05 (un solo candidato) y la validación de T10 con el fallback real del modelo.

## Limitaciones

- Los precios y el total del carrito son de demostración; no representan datos reales.
- El dataset Instacart no permite validar una tasa comercial de aceptación ≥ 12 % sin un A/B real; la interfaz muestra el `disclaimer` de métricas.
- No hay autenticación de usuario en el frontend (el backend actual no la implementa).
