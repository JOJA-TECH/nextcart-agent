export interface HealthResponse {
  status: string
  model_loaded: boolean
  model_version: string | null
  error: string | null
  catalog_loaded?: boolean
}

/**
 * Catálogo servido por el backend (/v1/catalog/*) desde SQLite construido
 * con los CSV del dataset Instacart. Los precios son valores de demostración
 * deterministas en COP (mismo product_id ⇒ mismo precio siempre).
 */
export interface CatalogProduct {
  product_id: number
  product_name: string
  aisle_id: number
  department_id: number
  price: number
  currency: "COP"
  aisle: string | null
  department: string | null
}

export interface CatalogPage {
  total: number
  limit: number
  offset: number
  items: CatalogProduct[]
}

export interface CatalogDepartment {
  department_id: number
  department: string
  product_count: number
}

export interface CatalogAisle {
  aisle_id: number
  aisle: string
  department_id: number | null
  product_count: number
}

export interface CatalogProductsQuery {
  search?: string
  department_id?: number
  aisle_id?: number
  limit?: number
  offset?: number
}

export type NavigationType = "view" | "reject" | "cart_add"

export interface NavigationItem {
  type: NavigationType
  product_id: number
}

export interface RecommendationRequest {
  session_id: string
  cart: number[]
  navigation?: NavigationItem[]
  recent_history?: number[][]
  rejected?: number[]
  inventory?: Record<string, boolean>
  k?: number
}

export type RecommendationSource =
  | "association_rule"
  | "global_frequency"
  | string

export interface Recommendation {
  product_id: number
  score: number
  reason: string
  source: RecommendationSource
}

export interface RecommendationResponse {
  session_id: string
  recommendations: Recommendation[]
  fallback: boolean
  model_version: string
  latency_ms: number
  warnings: string[]
}

export interface ImpressionEvent {
  session_id: string
  recommendation_ids: number[]
  cart: number[]
  model_version: string
}

export type FeedbackKind = "accepted" | "rejected" | "ignored"

export interface FeedbackEvent {
  session_id: string
  product_id: number
  event: FeedbackKind
  recommendation_ids: number[]
}

export interface MetricsSummary {
  impressions: number
  accepted: number
  rejected: number
  ignored: number
  acceptance_rate_observed: number | null
  catalog_coverage_observed: number
  latency_mean_ms: number
  latency_p95_ms: number
  errors: number
  model_version: string | null
  disclaimer: string
}

export interface NextCartClient {
  health(): Promise<HealthResponse>
  recommendations(
    request: RecommendationRequest,
  ): Promise<RecommendationResponse>
  impression(event: ImpressionEvent): Promise<void>
  feedback(event: FeedbackEvent): Promise<void>
  metricsSummary(): Promise<MetricsSummary>
  catalogProducts(query?: CatalogProductsQuery): Promise<CatalogPage>
  catalogDepartments(): Promise<CatalogDepartment[]>
  catalogAisles(departmentId?: number): Promise<CatalogAisle[]>
  catalogProduct(productId: number): Promise<CatalogProduct>
}
