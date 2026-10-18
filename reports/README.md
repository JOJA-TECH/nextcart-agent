# reports/ — resultados persistidos de la ejecución local

Todo lo que producen los scripts locales queda aquí y puede revisarse
después de la ejecución, sin volver a correr nada.

| Archivo | Generado por | Contenido |
|---|---|---|
| `audit_results.json` | `src/audit_dataset.py` | Inventario de archivos, resultado de S1–S5 con métricas, interpretación y limitaciones, y la decisión (`dataset_usable`, `status`, riesgos). |
| `dataset_audit.md` | `src/audit_dataset.py` | Informe legible: decisión, método, tabla S1–S5, explicación de métricas, interpretación de cada figura, limitaciones, riesgos de leakage y conclusión. |
| `model_metrics.json` | `src/evaluate_agent.py` | Evaluación offline del modelo vs `TopFreq` y `Cooccur`: Precision/Recall/HitRate/MAP @K (1,3,5,10), cobertura, repeat/explore, latencia, metodología del split y advertencias. |
| `figures/*.png` | ambos scripts | `orders_per_user`, `days_since_prior`, `split_composition`, `basket_size_distribution`, `product_frequency_longtail`, `cooccurrence_support_hist`, `s5_leakage_checks`, `model_metrics_at_k`, `repeat_explore_share`. |

Regenerar todo localmente:

```bash
python src/audit_dataset.py --data-dir dataset --output-dir reports
python src/train_agent.py --data-dir dataset --output artifacts/nextcart_model.json --metrics-output reports/model_metrics.json
python src/evaluate_agent.py --data-dir dataset --model artifacts/nextcart_model.json --output reports/model_metrics.json
```

> Las métricas de `model_metrics.json` son **offline** (predicción de cesta en el
> split prior/train). No miden aceptación ni conversión: el objetivo comercial de
> 12 % solo puede validarse con un A/B real de dos semanas en producción
> (Instacart no contiene impresiones, exposición ni grupo control).
