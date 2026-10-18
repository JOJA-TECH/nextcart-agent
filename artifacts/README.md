# artifacts/ — modelo entrenado y su manifiesto

Esta carpeta contiene el **artefacto entregable** del flujo local:
el modelo ya entrenado, no código de entrenamiento.

```
artifacts/
├── nextcart_model.json      # modelo (frecuencia + coocurrencia), JSON auditable
└── artifact_manifest.json   # versión, fecha, dataset fuente y sha256 del modelo
```

El modelo incluye:

- `model_version`, `trained_at_utc`, `algorithm`, `parameters`
- `popular_products`: fallback de popularidad global (con recencia relativa)
- `association_rules`: reglas co-ocurrencia por antecedente `[consecuente, count, confidence, lift]`
- `catalog_metadata`: catálogo, pasillos y departamentos para filtros
- `training_statistics` y `status`: `candidate` (producción) o `experimental`

Reglas del flujo:

- El backend y `src/inference.py` **solo cargan** este artefacto; nunca reentrenan.
- `artifact_manifest.json` se verifica (existencia, versión, hash sha256).
  Si el hash del modelo no coincide con el manifiesto, la carga falla de forma
  explícita: el artefacto pudo haberse modificado.
- Para usar el modelo, apunta `NEXTCART_MODEL_PATH` a él.

## Cómo generar/entregar los artefactos en tu equipo local

1. Ejecuta el flujo completo **con el dataset real** (auditoría → entrenamiento → evaluación):

```bash
python src/audit_dataset.py --data-dir dataset --output-dir reports
python src/train_agent.py --data-dir dataset \
    --output artifacts/nextcart_model.json \
    --metrics-output reports/model_metrics.json \
    --seed 42 --min-support 5 --top-k 100
python src/evaluate_agent.py --data-dir dataset \
    --model artifacts/nextcart_model.json --output reports/model_metrics.json
```

2. Copia **desde la máquina donde corrió el entrenamiento** estos archivos
   (son los entregables de la ejecución local):

```bash
artifacts/nextcart_model.json        # y artifacts/artifact_manifest.json
reports/audit_results.json
reports/model_metrics.json
reports/dataset_audit.md
reports/figures/*.png
```

Si hubiera una segunda máquina, `scp`/`rsync` del directorio `artifacts/` basta;
el manifiesto permite validar integridad al llegar.
