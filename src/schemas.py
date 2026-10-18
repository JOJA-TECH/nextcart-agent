"""Contratos Pydantic del agente NEXTCART: solicitudes, respuestas y eventos."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, StrictBool, field_validator

FeedbackLiteral = Literal["accepted", "rejected", "ignored"]
NAVIGATION_TYPES = ("view", "reject", "cart_add")


def _positive_ids(values: list[int]) -> list[int]:
    for v in values:
        if v <= 0:
            raise ValueError(f"los IDs deben ser enteros positivos, recibido: {v}")
    return values


def _dedupe_preserve_order(values: list[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


class NavigationEvent(BaseModel):
    type: Literal["view", "reject", "cart_add"]
    product_id: int = Field(gt=0)


class RecommendationRequest(BaseModel):
    session_id: str = Field(min_length=1)
    cart: list[int] = Field(default_factory=list)
    navigation: list[NavigationEvent] = Field(default_factory=list)
    recent_history: list[list[int]] = Field(default_factory=list)
    rejected: list[int] = Field(default_factory=list)
    # StrictBool: evita que Pydantic coerzone "yes"/"true"/1 a booleano.
    # Inventario debevenir del sistema real de la tienda, no de texto libre.
    inventory: dict[str, StrictBool] = Field(default_factory=dict)
    k: int = Field(default=3, ge=1, le=10)

    @field_validator("session_id")
    @classmethod
    def _session_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("session_id no puede ser vacío ni de solo espacios")
        return v.strip()

    @field_validator("cart", "rejected")
    @classmethod
    def _cart_ids(cls, v: list[int]) -> list[int]:
        return _dedupe_preserve_order(_positive_ids(v))

    @field_validator("recent_history")
    @classmethod
    def _history_ids(cls, v: list[list[int]]) -> list[list[int]]:
        cleaned = [_dedupe_preserve_order(_positive_ids(b)) for b in v]
        return [b for b in cleaned if b]

    @field_validator("inventory")
    @classmethod
    def _inventory_keys(cls, v: dict[str, bool]) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for key, available in v.items():
            if not isinstance(available, bool):
                raise ValueError(f"inventario['{key}'] debe ser booleano")
            try:
                pid = int(key)
            except ValueError as exc:
                raise ValueError(
                    f"inventario tiene clave no numérica: '{key}'"
                ) from exc
            if pid <= 0:
                raise ValueError(f"inventario tiene clave no positiva: '{key}'")
            out[str(pid)] = available
        return out


class RecommendationItem(BaseModel):
    product_id: int
    score: float
    reason: str
    source: Literal["association_rule", "global_frequency"]


class RecommendationResponse(BaseModel):
    session_id: str
    recommendations: list[RecommendationItem]
    fallback: bool
    model_version: str
    latency_ms: float
    warnings: list[str] = Field(default_factory=list)


class ImpressionEvent(BaseModel):
    session_id: str = Field(min_length=1)
    recommendation_ids: list[int] = Field(min_length=1)
    cart: list[int] = Field(default_factory=list)
    model_version: str = ""

    @field_validator("session_id")
    @classmethod
    def _session_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("session_id no puede ser vacío")
        return v.strip()

    @field_validator("recommendation_ids")
    @classmethod
    def _rec_ids(cls, v: list[int]) -> list[int]:
        return _dedupe_preserve_order(_positive_ids(v))

    @field_validator("cart")
    @classmethod
    def _cart_ids(cls, v: list[int]) -> list[int]:
        return _dedupe_preserve_order(_positive_ids(v))


class FeedbackEvent(BaseModel):
    session_id: str = Field(min_length=1)
    product_id: int = Field(gt=0)
    event: FeedbackLiteral
    recommendation_ids: list[int] = Field(default_factory=list)

    @field_validator("session_id")
    @classmethod
    def _session_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("session_id no puede ser vacío")
        return v.strip()

    @field_validator("recommendation_ids")
    @classmethod
    def _rec_ids(cls, v: list[int]) -> list[int]:
        return _dedupe_preserve_order(_positive_ids(v))


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    model_loaded: bool
    model_version: str | None = None
    error: str | None = None


class MetricsSummary(BaseModel):
    impressions: int
    accepted: int
    rejected: int
    ignored: int
    acceptance_rate_observed: float | None
    catalog_coverage_observed: float
    latency_mean_ms: float
    latency_p95_ms: float
    errors: int
    model_version: str | None
    disclaimer: str


class ReloadResponse(BaseModel):
    reloaded: bool
    model_version: str | None
    detail: str
