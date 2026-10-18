import type {
  FeedbackEvent,
  HealthResponse,
  ImpressionEvent,
  MetricsSummary,
  NextCartClient,
  RecommendationRequest,
  RecommendationResponse,
} from "@/shared/api/contracts"

/**
 * Envoltura de NextCartClient que registra en el panel de diagnóstico cada
 * llamada real hecha al backend. No simula ni altera respuestas.
 */
export class InstrumentedNextCartClient implements NextCartClient {
  private readonly inner: NextCartClient
  private readonly log: (entry: {
    method: string
    path: string
    status: number | null
    ok: boolean
    detail?: string
  }) => void

  constructor(inner: NextCartClient, log: (entry: {
    method: string
    path: string
    status: number | null
    ok: boolean
    detail?: string
  }) => void) {
    this.inner = inner
    this.log = log
  }

  async health(): Promise<HealthResponse> {
    try {
      const result = await this.inner.health()
      this.log({ method: "GET", path: "/health", status: 200, ok: true })
      return result
    } catch (error) {
      this.log({
        method: "GET",
        path: "/health",
        status: null,
        ok: false,
        detail: error instanceof Error ? error.message : String(error),
      })
      throw error
    }
  }

  async recommendations(request: RecommendationRequest): Promise<RecommendationResponse> {
    try {
      const result = await this.inner.recommendations(request)
      this.log({ method: "POST", path: "/v1/recommendations", status: 200, ok: true })
      return result
    } catch (error) {
      this.log({
        method: "POST",
        path: "/v1/recommendations",
        status: statusOf(error),
        ok: false,
        detail: error instanceof Error ? error.message : String(error),
      })
      throw error
    }
  }

  async impression(event: ImpressionEvent): Promise<void> {
    try {
      await this.inner.impression(event)
      this.log({ method: "POST", path: "/v1/events/impression", status: 202, ok: true })
    } catch (error) {
      this.log({
        method: "POST",
        path: "/v1/events/impression",
        status: statusOf(error),
        ok: false,
        detail: error instanceof Error ? error.message : String(error),
      })
      throw error
    }
  }

  async feedback(event: FeedbackEvent): Promise<void> {
    try {
      await this.inner.feedback(event)
      this.log({ method: "POST", path: "/v1/events/feedback", status: 202, ok: true })
    } catch (error) {
      this.log({
        method: "POST",
        path: "/v1/events/feedback",
        status: statusOf(error),
        ok: false,
        detail: error instanceof Error ? error.message : String(error),
      })
      throw error
    }
  }

  async metricsSummary(): Promise<MetricsSummary> {
    try {
      const result = await this.inner.metricsSummary()
      this.log({ method: "GET", path: "/v1/metrics/summary", status: 200, ok: true })
      return result
    } catch (error) {
      this.log({
        method: "GET",
        path: "/v1/metrics/summary",
        status: null,
        ok: false,
        detail: error instanceof Error ? error.message : String(error),
      })
      throw error
    }
  }
}

function statusOf(error: unknown): number | null {
  if (error != null && typeof error === "object" && "status" in error) {
    const status = (error as { status?: unknown }).status
    if (typeof status === "number") return status
  }
  return null
}
