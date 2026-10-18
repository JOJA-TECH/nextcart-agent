/**
 * Nota sobre el origen de los datos del catálogo.
 *
 * Productos: catálogo real del dataset Instacart servido por el backend
 * (/v1/catalog, SQLite construido desde los CSV del dataset).
 * Precios: valores de demostración deterministas en COP (el dataset no
 * incluye precios): mismo product_id ⇒ mismo precio siempre.
 * Imágenes: placeholder único de canasta de comida (icono).
 */
export const CATALOG_DATA_NOTE =
  "Los productos provienen del dataset Instacart vía /v1/catalog (SQLite). El dataset no incluye precios ni imágenes: los precios son de demostración determinista (mismo producto ⇒ mismo precio) y la imagen es un placeholder de canasta."

export const PLACEHOLDER_IMAGE_NOTE =
  "El dataset Instacart no incluye imágenes de producto; se usa un placeholder de canasta de comida."
