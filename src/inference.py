"""Inferencia local con el artefacto NEXTCART ya entrenado.

Cargar un modelo NO es entrenarlo: este módulo solo lee el JSON generado por
`src/train_agent.py`, verifica su manifiesto y aplica las reglas aprendidas a
un estado de sesión (carrito, navegación, historial, rechazos, inventario).

Ejemplos:
    python src/inference.py --model artifacts/nextcart_model.json --demo
    python src/inference.py --model artifacts/nextcart_model.json \
        --cart 24852,13176 --history "[[24852,13176],[47209]]" --k 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.artifacts import ModelLoadError, load_model_json, verify_manifest
from src.config import PROJECT_ROOT
from src.schemas import RecommendationRequest
from src.storage import now_utc_iso

REASON_RULE = "coocurrencia con el carrito"
REASON_RULE_NAV = "coocurrencia con navegación reciente"
REASON_POPULAR = "producto frecuente globalmente"
REASON_FALLBACK_EMPTY = "fallback de popularidad (carrito vacío)"
REASON_FALLBACK_NO_CANDIDATES = "fallback de popularidad (sin candidatos tras filtros)"


class NextCartRecommender:
    """Motor de recomendación basado en el artefacto JSON (sin reentrenamiento)."""

    def __init__(self, model: dict[str, Any]) -> None:
        self.model = model
        params = model.get("parameters", {})
        self.pop_weight = float(params.get("pop_weight", 0.15))
        self.repeat_boost = float(params.get("repeat_boost", 0.25))
        self.nav_weight = float(params.get("nav_weight", 0.5))
        self.rejection_penalty = float(params.get("rejection_penalty", 0.2))
        self.lift_cap = float(params.get("lift_cap", 5.0))
        self.history_items_used = int(params.get("history_items_used", 50))
        self.rules: dict[int, list[tuple[int, int, float, float]]] = {
            int(antecedent): [
                (int(r[0]), int(r[1]), float(r[2]), float(r[3])) for r in rule_list
            ]
            for antecedent, rule_list in model.get("association_rules", {}).items()
        }
        self.popular: list[dict[str, Any]] = model.get("popular_products", [])
        self.popular_ids: list[int] = [p["product_id"] for p in self.popular]
        self.pop_norm: dict[int, float] = {
            p["product_id"]: float(p["score"]) for p in self.popular
        }
        self.catalog_size = len(model.get("catalog_metadata", {}).get("products", {}))
        self.model_version = str(model.get("model_version", "unknown"))

    @classmethod
    def load(
        cls,
        model_path: Path | str,
        manifest_path: Path | str | None = None,
        verify: bool = True,
    ) -> "NextCartRecommender":
        model = load_model_json(model_path)
        if verify:
            verify_manifest(model_path, manifest_path)
        return cls(model)

    def _available(self, pid: int, inventory: dict[int, bool] | None) -> bool:
        if inventory is None:
            return True
        return inventory.get(pid, True)

    def _popular_fallback(
        self, exclude: set[int], k: int, inventory: dict[int, bool] | None, reason: str
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for pid in self.popular_ids:
            if pid in exclude:
                continue
            if not self._available(pid, inventory):
                continue
            out.append(
                {
                    "product_id": pid,
                    "score": round(self.pop_norm.get(pid, 0.0), 6),
                    "reason": reason,
                    "source": "global_frequency",
                }
            )
            if len(out) >= k:
                break
        return out

    def recommend(
        self, request: RecommendationRequest | dict[str, Any]
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        if isinstance(request, dict):
            request = RecommendationRequest.model_validate(request)
        warnings: list[str] = []

        cart = list(dict.fromkeys(request.cart))
        rejected = set(request.rejected)
        inventory = (
            {int(k): v for k, v in request.inventory.items()}
            if request.inventory
            else None
        )
        nav_views = [e.product_id for e in request.navigation if e.type == "view"]
        nav_rejects = [e.product_id for e in request.navigation if e.type == "reject"]
        for pid in nav_rejects:
            rejected.add(pid)

        history_items: list[int] = []
        for basket in request.recent_history:
            history_items.extend(basket)
        history_set = set(history_items)

        exclude = set(cart) | rejected
        context: list[tuple[int, float]] = [(pid, 1.0) for pid in cart]
        context += [
            (pid, 1.0)
            for pid in history_items[-self.history_items_used :]
            if pid not in cart
        ]
        context += [
            (pid, self.nav_weight)
            for pid in nav_views
            if pid not in cart and pid not in history_set
        ]

        if not context:
            recs = self._popular_fallback(
                exclude, request.k, inventory, REASON_FALLBACK_EMPTY
            )
            warnings.append(
                "carrito e historial vacíos; se usó fallback de popularidad"
            )
            fallback = True
        else:
            candidates: dict[int, dict[str, Any]] = {}
            has_cart = bool(cart)
            for pid, weight in context:
                for cons, count, conf, lift in self.rules.get(pid, ()):
                    if cons in exclude:
                        continue
                    capped_lift = min(lift, self.lift_cap)
                    contribution = (
                        weight * conf * (0.5 + 0.5 * capped_lift / self.lift_cap)
                    )
                    entry = candidates.get(cons)
                    if entry is None or contribution > entry["base"]:
                        candidates[cons] = {
                            "base": contribution,
                            "lift": capped_lift,
                            "count": count,
                            "from_nav": weight < 1.0 and not has_cart,
                        }
            scored: list[dict[str, Any]] = []
            for pid, entry in candidates.items():
                if not self._available(pid, inventory):
                    continue
                score = entry["base"] + self.pop_weight * self.pop_norm.get(pid, 0.0)
                source = "association_rule"
                reason = REASON_RULE_NAV if entry["from_nav"] else REASON_RULE
                if pid in history_set:
                    score += self.repeat_boost * self.pop_norm.get(pid, 0.0)
                if pid in rejected:
                    score *= self.rejection_penalty
                scored.append(
                    {
                        "product_id": pid,
                        "score": round(score, 6),
                        "reason": reason,
                        "source": source,
                    }
                )
            scored.sort(key=lambda r: (-r["score"], r["product_id"]))
            recs = scored[: request.k]
            if len(recs) < request.k:
                fill = self._popular_fallback(
                    exclude | {r["product_id"] for r in recs},
                    request.k - len(recs),
                    inventory,
                    REASON_POPULAR,
                )
                for r in fill:
                    r["score"] = round(r["score"] * 0.5, 6)
                recs.extend(fill)
            fallback = not scored
            if fallback:
                warnings.append(
                    "sin candidatos de coocurrencia tras filtros; "
                    "se usó fallback de popularidad"
                )
                if not recs:
                    recs = self._popular_fallback(
                        exclude - rejected,
                        request.k,
                        None,
                        REASON_FALLBACK_NO_CANDIDATES,
                    )
                    warnings.append(
                        "inventario o rechazos vaciaron los candidatos; "
                        "el fallback ignora esos filtros"
                    )
            if cart and not history_items:
                warnings.append(
                    "usuario sin historial reciente (cold start); "
                    "se confía en coocurrencia del carrito y popularidad"
                )
            if any(not self._available(pid, inventory) for pid in cart):
                warnings.append(
                    "el carrito contiene productos no catalogados o agotados"
                )

        latency_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "session_id": request.session_id,
            "recommendations": recs[: request.k],
            "fallback": fallback,
            "model_version": self.model_version,
            "latency_ms": round(latency_ms, 3),
            "warnings": warnings,
            "generated_at_utc": now_utc_iso(),
        }


DEMO_REQUESTS: list[dict[str, Any]] = [
    {
        "name": "carrito normal con historial",
        "payload": {
            "session_id": "demo-001",
            "cart": [24852, 13176],
            "navigation": [{"type": "view", "product_id": 47209}],
            "recent_history": [[24852, 13176], [47209]],
            "rejected": [22935],
            "inventory": {"21137": True, "22935": False},
            "k": 3,
        },
    },
    {
        "name": "carrito vacío",
        "payload": {"session_id": "demo-002", "cart": [], "k": 3},
    },
    {
        "name": "usuario sin historial",
        "payload": {"session_id": "demo-003", "cart": [24852, 13176], "k": 3},
    },
    {
        "name": "producto rechazado y agotado",
        "payload": {
            "session_id": "demo-004",
            "cart": [24852],
            "rejected": [13176],
            "inventory": {"13176": False},
            "k": 3,
        },
    },
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prueba el modelo NEXTCART ya entrenado (carga el artefacto; "
        "no entrena).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "nextcart_model.json",
        help="Ruta del artefacto de modelo.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Ruta del manifiesto (por defecto: junto al modelo).",
    )
    parser.add_argument(
        "--no-verify", action="store_true", help="Omite la verificación del manifiesto."
    )
    parser.add_argument(
        "--cart",
        type=str,
        default=None,
        help="IDs del carrito separados por coma (p. ej. 24852,13176).",
    )
    parser.add_argument(
        "--history",
        type=str,
        default=None,
        help='Historial como JSON de listas: "[[1,2],[3]]".',
    )
    parser.add_argument(
        "--rejected", type=str, default=None, help="IDs rechazados separados por coma."
    )
    parser.add_argument(
        "--inventory",
        type=str,
        default=None,
        help='Inventario como JSON: "{\\"21137\\": true}".',
    )
    parser.add_argument("--session-id", type=str, default="cli-session")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Ejecuta los escenarios de ejemplo (carrito normal, "
        "vacío, cold start, filtros).",
    )
    return parser.parse_args(argv)


def _parse_int_list(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rec = NextCartRecommender.load(
            args.model, args.manifest, verify=not args.no_verify
        )
    except ModelLoadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(
            "\nInstrucciones:\n"
            "  1. En el equipo con el dataset, ejecuta: "
            "python src/train_agent.py --data-dir dataset --output artifacts/nextcart_model.json\n"
            "  2. Copia artifacts/nextcart_model.json (y artifact_manifest.json) "
            "a esta máquina.\n"
            "  3. Reejecuta este comando.",
            file=sys.stderr,
        )
        return 2
    print(
        f"Modelo cargado: {rec.model_version} "
        f"(algoritmo={rec.model.get('algorithm')}, reglas={len(rec.rules)}, "
        f"populares={len(rec.popular)}) — solo lectura, sin reentrenamiento."
    )

    if args.demo:
        for scenario in DEMO_REQUESTS:
            result = rec.recommend(scenario["payload"])
            print(f"\n--- Escenario: {scenario['name']} ---")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    payload: dict[str, Any] = {
        "session_id": args.session_id,
        "cart": _parse_int_list(args.cart),
        "k": args.k,
        "rejected": _parse_int_list(args.rejected),
    }
    if args.history:
        payload["recent_history"] = json.loads(args.history)
    if args.inventory:
        payload["inventory"] = json.loads(args.inventory)
    print(json.dumps(rec.recommend(payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
