import type {
  CatalogAisle,
  CatalogDepartment,
  CatalogPage,
  CatalogProduct,
  CatalogProductsQuery,
  FeedbackEvent,
  HealthResponse,
  ImpressionEvent,
  MetricsSummary,
  NextCartClient,
  RecommendationRequest,
  RecommendationResponse,
} from "./contracts"

export class NextCartApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "NextCartApiError"
    this.status = status
  }
}

export class NextCartConnectionError extends Error {
  constructor() {
    super("No se pudo conectar con el backend FastAPI.")
    this.name = "NextCartConnectionError"
  }
}

// Misma-origen por defecto: en desarrollo el proxy de Vite (vite.config.ts)
// reenvía /v1 y /health al backend. Con VITE_NEXTCART_API_BASE_URL se llama
// directo (el backend ya habilita CORS para localhost:5173/4173).
const API_BASE_URL: string = import.meta.env.VITE_NEXTCART_API_BASE_URL ?? ""

export function getApiBaseUrl(): string {
  return API_BASE_URL
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    })
  } catch {
    throw new NextCartConnectionError()
  }

  if (!response.ok) {
    let detail = `Error HTTP ${response.status}`
    try {
      const body: unknown = await response.json()
      if (
        body != null &&
        typeof body === "object" &&
        "detail" in body &&
        (typeof body.detail === "string" || Array.isArray(body.detail))
      ) {
        detail = formatValidationDetail(body.detail, detail)
      }
    } catch {
      // keep the HTTP status message when the body is not readable JSON
    }
    throw new NextCartApiError(response.status, detail)
  }

  if (response.status === 202) {
    return undefined as T
  }
  return (await response.json()) as T
}

function formatValidationDetail(detail: string | unknown[], fallback: string): string {
  if (typeof detail === "string") return detail
  if (!Array.isArray(detail)) return fallback
  return detail
    .map((item) => {
      if (item != null && typeof item === "object") {
        const record = item as Record<string, unknown>
        const loc = Array.isArray(record.loc)
          ? record.loc.filter((part) => part !== "body").join(".")
          : ""
        const msg = typeof record.msg === "string" ? record.msg : ""
        return loc ? `${loc}: ${msg}` : msg
      }
      return String(item)
    })
    .join(" | ")
}

export class HttpNextCartClient implements NextCartClient {
  health(): Promise<HealthResponse> {
    return request<HealthResponse>("/health")
  }

  recommendations(
    payload: RecommendationRequest,
  ): Promise<RecommendationResponse> {
    return request<RecommendationResponse>("/v1/recommendations", {
      method: "POST",
      body: JSON.stringify(payload),
    })
  }

  async impression(event: ImpressionEvent): Promise<void> {
    await request<void>("/v1/events/impression", {
      method: "POST",
      body: JSON.stringify(event),
    })
  }

  async feedback(event: FeedbackEvent): Promise<void> {
    await request<void>("/v1/events/feedback", {
      method: "POST",
      body: JSON.stringify(event),
    })
  }

  metricsSummary(): Promise<MetricsSummary> {
    return request<MetricsSummary>("/v1/metrics/summary")
  }

  catalogProducts(query: CatalogProductsQuery = {}): Promise<CatalogPage> {
    const params = new URLSearchParams()
    if (query.search?.trim()) params.set("search", query.search.trim())
    if (query.department_id !== undefined) {
      params.set("department_id", String(query.department_id))
    }
    if (query.aisle_id !== undefined) {
      params.set("aisle_id", String(query.aisle_id))
    }
    if (query.limit !== undefined) params.set("limit", String(query.limit))
    if (query.offset !== undefined) params.set("offset", String(query.offset))
    const qs = params.toString()
    return request<CatalogPage>(`/v1/catalog/products${qs ? `?${qs}` : ""}`)
  }

  async catalogDepartments(): Promise<CatalogDepartment[]> {
    const body = await request<{ items: CatalogDepartment[] }>(
      "/v1/catalog/departments",
    )
    return body.items
  }

  async catalogAisles(departmentId?: number): Promise<CatalogAisle[]> {
    const qs = departmentId !== undefined ? `?department_id=${departmentId}` : ""
    const body = await request<{ items: CatalogAisle[] }>(`/v1/catalog/aisles${qs}`)
    return body.items
  }

  catalogProduct(productId: number): Promise<CatalogProduct> {
    return request<CatalogProduct>(
      `/v1/catalog/products/${encodeURIComponent(productId)}`,
    )
  }
}
