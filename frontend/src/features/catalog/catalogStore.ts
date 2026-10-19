import { useEffect, useMemo, useSyncExternalStore } from "react"
import type {
  CatalogAisle,
  CatalogDepartment,
  CatalogPage,
  CatalogProduct,
  CatalogProductsQuery,
  NextCartClient,
} from "@/shared/api/contracts"

/**
 * Catálogo servido por el backend (/v1/catalog/*). Los datos provienen de
 * SQLite construido con los CSV del dataset Instacart; los precios son de
 * demostración determinista (mismo product_id ⇒ mismo precio siempre).
 *
 * Cache por módulo con suscripción externa (useSyncExternalStore): tarjetas
 * de recomendaciones, carrito y navegador de catálogo comparten el mismo
 * storage, así que cada product_id se pide al backend una sola vez por
 * sesión de página.
 */

interface QueryEntry<T = unknown> {
  data: T | null
  error: string | null
  loading: boolean
}

const store = new Map<number, CatalogProduct>()
const missing = new Set<number>()
const pendingProducts = new Map<number, Promise<CatalogProduct | null>>()
const queryCache = new Map<string, QueryEntry>()
const inFlightQueries = new Set<string>()

let version = 0
const listeners = new Set<() => void>()

function notify(): void {
  version += 1
  for (const listener of Array.from(listeners)) listener()
}

/* Entrada/salida del storage externo ------------------------------------ */

const getVersion = (): number => version
const subscribeStore = (listener: () => void): (() => void) => {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
/** Bump de versión: fuerza re-lectura de los snapshots cacheados. */
function useCatalogVersion(): void {
  useSyncExternalStore(subscribeStore, getVersion, getVersion)
}

/* Productos individuales ------------------------------------------------- */

function requestProduct(
  client: NextCartClient,
  productId: number,
): Promise<CatalogProduct | null> {
  const inFlight = pendingProducts.get(productId)
  if (inFlight) return inFlight
  const promise = client
    .catalogProduct(productId)
    .then((product) => {
      missing.delete(productId)
      store.set(product.product_id, product)
      return product
    })
    .catch(() => {
      // 404 u otro error: recordar la ausencia para no reintentar por render.
      missing.add(productId)
      return null
    })
    .finally(() => {
      pendingProducts.delete(productId)
      notify()
    })
  pendingProducts.set(productId, promise)
  return promise
}

export interface CatalogEntry {
  product: CatalogProduct | null
  /** true mientras el product_id se resuelve contra el backend. */
  loading: boolean
}

/**
 * Resuelve un product_id contra el catálogo del backend con cache compartido.
 * Devuelve `product: null` (con loading=false) si el producto no existe.
 */
export function useCatalogProduct(
  client: NextCartClient,
  productId: number,
): CatalogEntry {
  useCatalogVersion()
  const cached = store.get(productId)
  const knownMissing = missing.has(productId)
  const loading = !cached && !knownMissing

  useEffect(() => {
    if (!store.has(productId) && !missing.has(productId)) {
      void requestProduct(client, productId)
    }
  }, [client, productId])

  if (cached) return { product: cached, loading: false }
  return { product: null, loading }
}

// Prefetch en segundo plano (p. ej. para precargar IDs de una respuesta).
export function prefetchProduct(client: NextCartClient, productId: number): void {
  if (store.has(productId) || missing.has(productId)) return
  void requestProduct(client, productId)
}

/**
 * Suscripción al cache compartido: útil para agregados (p. ej. un total que
 * suma precios aún no resueltos en otras filas).
 */
export function useCatalogCacheSnapshot(): ReadonlyMap<number, CatalogProduct> {
  useCatalogVersion()
  return store
}

/* Consultas de listado (productos/pasillos/departamentos) ----------------- */

function runQuery(key: string, loader: () => Promise<unknown>): void {
  if (queryCache.has(key) || inFlightQueries.has(key)) return
  inFlightQueries.add(key)
  loader()
    .then((data) => {
      queryCache.set(key, { data, error: null, loading: false })
    })
    .catch((err: unknown) => {
      queryCache.set(key, {
        data: null,
        error: err instanceof Error ? err.message : String(err),
        loading: false,
      })
    })
    .finally(() => {
      inFlightQueries.delete(key)
      notify()
    })
}

const LOADING_ENTRY: QueryEntry = { data: null, error: null, loading: true }

function useCachedQuery<T>(key: string): QueryEntry<T> {
  useCatalogVersion()
  return (queryCache.get(key) ?? LOADING_ENTRY) as QueryEntry<T>
}

export function useCatalogDepartments(
  client: NextCartClient,
): QueryEntry<CatalogDepartment[]> {
  const key = "catalog:departments"
  useEffect(() => {
    runQuery(key, () => client.catalogDepartments())
     
  }, [client])
  return useCachedQuery<CatalogDepartment[]>(key)
}

export function useCatalogAisles(
  client: NextCartClient,
  departmentId: number | null,
): QueryEntry<CatalogAisle[]> {
  const key = `catalog:aisles:${departmentId ?? "all"}`
  useEffect(() => {
    runQuery(key, () => client.catalogAisles(departmentId ?? undefined))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, departmentId])
  return useCachedQuery<CatalogAisle[]>(key)
}

export function useCatalogList(
  client: NextCartClient,
  query: CatalogProductsQuery,
): QueryEntry<CatalogPage> {
  const key = useMemo(
    () => `catalog:products:${JSON.stringify(query)}`,
    [query],
  )
  useEffect(() => {
    runQuery(key, () => client.catalogProducts(query))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, key])
  return useCachedQuery<CatalogPage>(key)
}
