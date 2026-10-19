# Auditoría del dataset — NEXTCART (notebook independiente)

**Corrida:** 2026-10-18T16:26:42Z · **Seed:** 42 · **Dataset:** `/content/data`
· **Muestreo:** Sin muestreo: dataset completo.

## 1. Resumen de la decisión

- dataset_usable: **True** (`usable_with_restrictions`)
- Se puede entrenar y evaluar offline un recomendador de próxima cesta sobre el split oficial prior/train sin fuga de información. Restricción: el dataset no tiene inventario real, precios, exposición del widget ni aceptación; el objetivo de ≥ 12 % de aceptación solo puede medirse con un A/B real de dos semanas en producción.

## 2. Descripción del dataset

Cada `order_id` es una cesta y `order_number` ordena las compras de cada usuario. El split oficial marca por usuario una última orden `train` (ground truth público) o `test` (sin ground truth); todo lo anterior es `prior`.

## 3. Tabla de supuestos

| Supuesto | Descripción | Estado |
|---|---|---|
| S1_schema_integrity | Integridad de esquema, claves y referencias | **PASS** |
| S2_sequential_history | Historial secuencial reconstruible por usuario | **PASS** |
| S3_basket_density | Densidad de cestas y cola larga del catálogo | **PASS** |
| S4_complementarity_signal | Señal de coocurrencia y recompra | **PASS** |
| S5_leakage_free_evaluation | Evaluación sin fuga de información (leakage) | **PASS** |

## 4. Interpretación por supuesto

### S1_schema_integrity — PASS

Esquema completo, claves sin duplicados, sin huérfanos de referencia y nulos de days_since_prior_order solo en la primera compra (comportamiento esperado, no un error). Se pueden reconstruir cestas y secuencias sin imputación.

**Limitaciones:**
- No valida semántica del contenido (nombres de producto).
- order_hour_of_day llega como texto; se convierte con TRY_CAST.

### S2_sequential_history — PASS

Las secuencias de compra de cada usuario son continuas (order_number sin huecos) y el split oficial marca una única orden train, la más reciente: la predicción de próxima cesta es coherente temporalmente. El 59.0% de los ítems prior está marcado como reordenado: repeat/explore es una partición real del problema.

**Limitaciones:**
- No hay timestamps absolutos: solo order_number, dow/hora y days_since_prior_order; la recencia solo puede ser relativa.

### S3_basket_density — PASS

El 95.1% de las cestas prior tiene ≥ 2 productos (condición necesaria para coocurrencia) y la cesta media es de 10.1 productos: contar pares dentro de la cesta es barato. La cola larga del catálogo implica que el agente necesita un fallback de popularidad para cold start y productos sin reglas.

**Limitaciones:**
- Sin stock real: una cesta puede reflejar sustituciones, no demanda ideal.
- Miles de productos de cola quedarán sin reglas con min_support=5.

### S4_complementarity_signal — PASS

El 59.0% de los ítems prior está marcado como reordenado y el 87.9% de los ítems de cesta son repetidos en sentido estricto. En la muestra hay 10,994,767 pares distintos y el 11.3% alcanza soporte ≥ 5: hay masa suficiente para reglas explicables con min_support = 5. El histograma muestra la típica cola larga de asociaciones.

**Limitaciones:**
- El conteo de pares de S4 es por muestra (solo diagnóstico); el entrenamiento usa todas las cestas de la corrida.
- Coocurrencia no implica causalidad ni complementariedad comercial deliberada; solo asociación histórica.

### S5_leakage_free_evaluation — PASS

Split usable sin fuga: prior y train disjuntos, la orden train es la más reciente y toda orden prior ocurre estrictamente antes. Las reglas se entrenan solo con prior y la cesta objetivo nunca entra como variable. Los usuarios test quedan excluidos (sin ground truth público).

**Limitaciones:**
- El split valida predicción de cesta, no conversión comercial: Instacart no contiene impresiones, exposición ni aceptación.

## 5. Riesgos de leakage y preprocesamiento recomendado

- Entrenar únicamente con órdenes `prior`; la cesta objetivo nunca entra como variable.
- Cesta por `order_id`; secuencia con `order_number`.
- Fallback de popularidad para cold start y productos sin reglas.

## 6. Conclusión

El dataset es **apto** para entrenar y evaluar offline NEXTCART (`usable_with_restrictions`). El objetivo comercial de ≥ 12 % de aceptación **no** puede validarse con Instacart: exige un A/B real de dos semanas con grupo de control en producción.
