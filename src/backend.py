"""Backend FastAPI liviano de NEXTCART-AGENT.

Reglas de inicio (verificadas en tests):
- NO entrena al importar el módulo.
- NO descarga el dataset ni ejecuta flujos pesados al iniciar.
- Carga únicamente el artefacto de modelo ya entrenado (JSON + manifiesto),
  cuya ruta se configura con la variable de entorno NEXTCART_MODEL_PATH.
- Si el modelo falta o falla la verificación, expone model_loaded=false y los
  endpoints de recomendación responden 503 con instrucciones.

Arranque:
    export NEXTCART_MODEL_PATH=artifacts/nextcart_model.json
    uvicorn src.backend:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from src.artifacts import ModelLoadError
from src.config import DISCLAIMER_AB_TEST, PROJECT_ROOT
from src.inference import NextCartRecommender
from src.schemas import (
    FeedbackEvent,
    HealthResponse,
    ImpressionEvent,
    MetricsSummary,
    RecommendationRequest,
    RecommendationResponse,
    ReloadResponse,
)
from src.storage import append_jsonl, ensure_dir, now_utc_iso, read_json


class BackendState:
    def __init__(self) -> None:
        self.recommender: NextCartRecommender | None = None
        self.model_error: str | None = None
        self.model_path: Path | None = None
        self.events_path: Path = PROJECT_ROOT / "logs" / "events.jsonl"
        self.impressions = 0
        self.accepted = 0
        self.rejected_feedback = 0
        self.ignored = 0
        self.errors = 0
        self.latencies: list[float] = []
        self.recommended_ids: set[int] = set()

    def load_model(self, model_path: Path, manifest_path: Path | None = None) -> None:
        try:
            self.recommender = NextCartRecommender.load(model_path, manifest_path)
            self.model_error = None
            self.model_path = model_path
        except ModelLoadError as exc:
            self.recommender = None
            self.model_error = str(exc)

    def log_event(self, kind: str, payload: dict[str, Any]) -> None:
        append_jsonl(self.events_path, {"ts": now_utc_iso(), "type": kind, **payload})


def create_app(
    model_path: str | Path | None = None,
    events_path: str | Path | None = None,
    admin_token: str | None = None,
    manifest_path: str | Path | None = None,
) -> FastAPI:
    state = BackendState()
    env_model = model_path or os.environ.get("NEXTCART_MODEL_PATH")
    env_events = events_path or os.environ.get("NEXTCART_EVENTS_PATH")
    env_token = (
        admin_token
        if admin_token is not None
        else os.environ.get("NEXTCART_ADMIN_TOKEN")
    )
    env_manifest = manifest_path or os.environ.get("NEXTCART_MANIFEST_PATH")
    if env_events:
        state.events_path = Path(env_events)
    ensure_dir(state.events_path.parent)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if env_model:
            state.load_model(
                Path(env_model), Path(env_manifest) if env_manifest else None
            )
            if state.recommender:
                print(
                    f"[nextcart] modelo cargado: "
                    f"{state.recommender.model_version} desde {env_model}"
                )
            else:
                print(f"[nextcart] ERROR al cargar modelo: {state.model_error}")
        else:
            state.model_error = (
                "NEXTCART_MODEL_PATH no está definido. Exporta la ruta del artefacto "
                "entrenado, p. ej.: export NEXTCART_MODEL_PATH=artifacts/nextcart_model.json"
            )
            print(f"[nextcart] advertencia: {state.model_error}")
        yield

    app = FastAPI(title="NEXTCART-AGENT", version="0.1.0", lifespan=lifespan)
    # CORS para el frontend en desarrollo (Vite dev :5173 y preview :4173);
    # configurable con NEXTCART_CORS_ORIGINS (separada por comas) para otros
    # despliegues. En producción también se puede usar el proxy inverso.
    default_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
    raw_origins = os.environ.get("NEXTCART_CORS_ORIGINS")
    cors_origins = (
        [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
        if raw_origins
        else default_origins
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.nc = state
    app.state.admin_token = env_token

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        loaded = state.recommender is not None
        return HealthResponse(
            status="ok" if loaded else "degraded",
            model_loaded=loaded,
            model_version=state.recommender.model_version if loaded else None,
            error=None if loaded else state.model_error,
        )

    @app.post("/v1/recommendations", response_model=RecommendationResponse)
    def recommendations(req: RecommendationRequest) -> RecommendationResponse:
        if state.recommender is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "model_not_loaded",
                    "detail": state.model_error,
                    "instruction": (
                        "Entrena el modelo localmente con src/train_agent.py y define "
                        "NEXTCART_MODEL_PATH apuntando al artefacto; reinicia o usa "
                        "/v1/admin/reload-model."
                    ),
                },
            )
        try:
            result = state.recommender.recommend(req)
        except Exception as exc:
            state.errors += 1
            state.log_event(
                "error", {"endpoint": "recommendations", "error": str(exc)[:500]}
            )
            raise HTTPException(
                status_code=500,
                detail={"error": "inference_failed", "detail": str(exc)[:500]},
            ) from exc
        state.latencies.append(result["latency_ms"])
        state.recommended_ids.update(r["product_id"] for r in result["recommendations"])
        state.log_event(
            "recommendation",
            {
                "session_id": req.session_id,
                "k": req.k,
                "cart": req.cart,
                "recommendation_ids": [
                    r["product_id"] for r in result["recommendations"]
                ],
                "fallback": result["fallback"],
                "model_version": result["model_version"],
                "latency_ms": result["latency_ms"],
            },
        )
        return RecommendationResponse.model_validate(
            {k: v for k, v in result.items() if k != "generated_at_utc"}
        )

    @app.post("/v1/events/impression", status_code=202)
    def impression(ev: ImpressionEvent) -> dict[str, Any]:
        state.impressions += 1
        state.log_event(
            "impression",
            {
                "session_id": ev.session_id,
                "recommendation_ids": ev.recommendation_ids,
                "cart": ev.cart,
                "model_version": ev.model_version,
            },
        )
        return {"logged": True, "type": "impression"}

    @app.post("/v1/events/feedback", status_code=202)
    def feedback(ev: FeedbackEvent) -> dict[str, Any]:
        if ev.event == "accepted":
            state.accepted += 1
        elif ev.event == "rejected":
            state.rejected_feedback += 1
        else:
            state.ignored += 1
        state.log_event(
            "feedback",
            {
                "session_id": ev.session_id,
                "product_id": ev.product_id,
                "event": ev.event,
                "recommendation_ids": ev.recommendation_ids,
            },
        )
        return {"logged": True, "type": "feedback"}

    @app.get("/v1/metrics/summary", response_model=MetricsSummary)
    def metrics_summary() -> MetricsSummary:
        lat = sorted(state.latencies) or [0.0]
        p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))]
        catalog_size = 0
        if state.recommender:
            catalog_size = state.recommender.catalog_size or len(
                state.recommender.popular_ids
            )
        coverage = (len(state.recommended_ids) / catalog_size) if catalog_size else 0.0
        rate = (state.accepted / state.impressions) if state.impressions else None
        return MetricsSummary(
            impressions=state.impressions,
            accepted=state.accepted,
            rejected=state.rejected_feedback,
            ignored=state.ignored,
            acceptance_rate_observed=rate,
            catalog_coverage_observed=coverage,
            latency_mean_ms=float(sum(lat) / len(lat)),
            latency_p95_ms=float(p95),
            errors=state.errors,
            model_version=state.recommender.model_version
            if state.recommender
            else None,
            disclaimer=DISCLAIMER_AB_TEST,
        )

    @app.post("/v1/admin/reload-model", response_model=ReloadResponse)
    def reload_model(
        response: Response, x_admin_token: str | None = Header(default=None)
    ) -> ReloadResponse:
        if not env_token:
            raise HTTPException(
                status_code=404,
                detail="reload deshabilitado: define NEXTCART_ADMIN_TOKEN",
            )
        if x_admin_token != env_token:
            raise HTTPException(status_code=403, detail="token administrativo inválido")
        if not env_model:
            raise HTTPException(
                status_code=409, detail="NEXTCART_MODEL_PATH no está definido"
            )
        state.load_model(Path(env_model), Path(env_manifest) if env_manifest else None)
        if state.recommender is None:
            return ReloadResponse(
                reloaded=False,
                model_version=None,
                detail=state.model_error or "error desconocido",
            )
        return ReloadResponse(
            reloaded=True,
            model_version=state.recommender.model_version,
            detail=f"modelo recargado desde {env_model}",
        )

    return app


app = create_app()
