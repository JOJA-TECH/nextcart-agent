"""Carga/validación del artefacto de modelo y su manifiesto.

Este módulo NO entrena: solo lee artefactos ya generados localmente con
`src/train_agent.py` y verifica su integridad (existencia, versión, hash).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .config import MODEL_FORMAT_VERSION, PROJECT_ROOT
from .storage import now_utc_iso, read_json, sha256_of_file, write_json_atomic


class ModelLoadError(RuntimeError):
    """El artefacto solicitado no existe, está corrupto o no supera la verificación."""


def training_code_version() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=False, cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "0.1.0"


def load_model_json(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise ModelLoadError(
            f"No existe el artefacto de modelo en '{path}'. "
            "Ejecuta localmente: python src/train_agent.py --data-dir dataset "
            "--output ../artifacts/nextcart_model.json"
        )
    try:
        model = read_json(path)
    except Exception as exc:
        raise ModelLoadError(f"El modelo '{path}' no es JSON válido: {exc}") from exc
    required = {
        "model_version",
        "algorithm",
        "parameters",
        "popular_products",
        "association_rules",
        "catalog_metadata",
    }
    missing = required - set(model)
    if missing:
        raise ModelLoadError(
            f"El modelo '{path}' carece de campos obligatorios: {sorted(missing)}"
        )
    if model.get("format_version", MODEL_FORMAT_VERSION) > MODEL_FORMAT_VERSION:
        raise ModelLoadError(
            f"El modelo '{path}' usa formato {model.get('format_version')} "
            f"pero solo se soporta <= {MODEL_FORMAT_VERSION}."
        )
    return model


def default_manifest_path(model_path: Path | str) -> Path:
    return Path(model_path).resolve().parent / "artifact_manifest.json"


def verify_manifest(
    model_path: Path | str, manifest_path: Path | str | None = None
) -> dict[str, Any]:
    """Verifica existencia, versión y hash del modelo contra el manifiesto.

    Si el manifiesto no existe, se devuelve un dict vacío (verificación
    incompleta, no bloqueante). Si existe y el hash o la versión no coinciden,
    se lanza ModelLoadError.
    """
    model_path = Path(model_path)
    mpath = Path(manifest_path) if manifest_path else default_manifest_path(model_path)
    if not mpath.is_file():
        return {}
    try:
        manifest = read_json(mpath)
    except Exception as exc:
        raise ModelLoadError(f"Manifiesto ilegible en '{mpath}': {exc}") from exc
    expected_hash = manifest.get("sha256")
    if expected_hash:
        actual = sha256_of_file(model_path)
        if actual != expected_hash:
            raise ModelLoadError(
                f"Hash del modelo '{model_path.name}' no coincide con el manifiesto "
                f"('{mpath}'). Esperado {expected_hash[:12]}…, obtenido {actual[:12]}…. "
                "El artefacto pudo haber sido modificado; reentrena o copia el archivo correcto."
            )
    if manifest.get("model_version") and not model_path.stem.startswith("__"):
        try:
            model = read_json(model_path)
            if model.get("model_version") != manifest["model_version"]:
                raise ModelLoadError(
                    f"Versión del modelo ({model.get('model_version')}) difiere de la "
                    f"del manifiesto ({manifest['model_version']})."
                )
        except ModelLoadError:
            raise
        except Exception:
            pass
    return manifest


def write_manifest(
    model_path: Path | str,
    model: dict[str, Any],
    *,
    source_dataset: str,
    audit_results_path: str | None,
    metrics_path: str | None,
    manifest_path: Path | str | None = None,
) -> Path:
    model_path = Path(model_path)
    mpath = Path(manifest_path) if manifest_path else default_manifest_path(model_path)
    payload = {
        "model_path": model_path.name,
        "model_version": model["model_version"],
        "created_at_utc": now_utc_iso(),
        "source_dataset": source_dataset,
        "training_code_version": training_code_version(),
        "audit_results_path": audit_results_path,
        "metrics_path": metrics_path,
        "sha256": sha256_of_file(model_path),
    }
    write_json_atomic(mpath, payload)
    return mpath
