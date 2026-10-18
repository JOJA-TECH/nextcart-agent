export interface HealthResponse {
  status: string
  model_loaded: boolean
  model_version: string | null
  error: string | null
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
  model_version: string | null
  latency_ms: number
  warnings: string[]
}

export interface ImpressionEvent {
  session_id: string
  recommendation_ids: number[]
  cart: number[]
  model_version: string | null
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
  acceptance_rate_observed: number
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
}
