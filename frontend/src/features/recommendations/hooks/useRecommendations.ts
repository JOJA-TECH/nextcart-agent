import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type {
  FeedbackKind,
  NextCartClient,
  RecommendationResponse,
} from "@/shared/api/contracts"
import { describeApiError } from "@/shared/api/api-activity-log"

export type RequestStatus = "idle" | "loading" | "success" | "error"

export interface UseRecommendationsResult {
  status: RequestStatus
  response: RecommendationResponse | null
  error: string | null
  acceptedIds: number[]
  rejectedIds: number[]
  ignoredIds: number[]
  acceptedNow: number | null
  fetchRecommendations(options?: {
    cartOverride?: number[]
    inventoryOverride?: Record<string, boolean>
    k?: number
    invalidRequest?: boolean
  }): Promise<void>
  sendFeedback(productId: number, kind: FeedbackKind): Promise<boolean>
  reset(): void
}

const DEFAULT_INVENTORY: Record<string, boolean> = {
  "21137": true,
  "22935": false,
}

export function useRecommendations(
  client: NextCartClient,
  sessionId: string,
  cart: number[],
  onBackendEvent?: () => void,
): UseRecommendationsResult {
  const [status, setStatus] = useState<RequestStatus>("idle")
  const [response, setResponse] = useState<RecommendationResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [acceptedIds, setAcceptedIds] = useState<number[]>([])
  const [rejectedIds, setRejectedIds] = useState<number[]>([])
  const [ignoredIds, setIgnoredIds] = useState<number[]>([])
  const [acceptedNow, setAcceptedNow] = useState<number | null>(null)
  const impressionSentRef = useRef<RecommendationResponse | null>(null)
  const hasFetchedRef = useRef(false)
  // Ref siempre fresco: una re-consulta disparada justo después de votar
  // debe incluir el rechazo recién registrado.
  const rejectedRef = useRef(rejectedIds)

  const effectiveCart = useMemo(() => {
    if (cart.length > 0) return cart
    // T09: carrito vacío — se envía [] real al backend y se deja que el
    // backend decida (fallback + warnings). No se sustituye localmente.
    return []
  }, [cart])

  const fetchRecommendations = useCallback(
    async (options?: {
      cartOverride?: number[]
      inventoryOverride?: Record<string, boolean>
      k?: number
      invalidRequest?: boolean
    }) => {
      setStatus("loading")
      setError(null)
      try {
        // T08: cuando invalidRequest es true se envía k=99 real para provocar
        // un HTTP 422 del backend y mostrar el error legible.
        const payload = {
          session_id: sessionId,
          cart: options?.cartOverride ?? effectiveCart,
          navigation: [] as { type: "view"; product_id: number }[],
          recent_history: [effectiveCart] as number[][],
          rejected: rejectedRef.current,
          inventory:
            options?.inventoryOverride ??
            DEFAULT_INVENTORY,
          ...(options?.invalidRequest ? { k: 99 } : { k: options?.k ?? 4 }),
        }
        const result = await client.recommendations(payload)
        setResponse(result)
        setStatus("success")
        impressionSentRef.current = null
        hasFetchedRef.current = true
        onBackendEvent?.()
      } catch (err) {
        setError(describeApiError(err))
        setStatus("error")
        onBackendEvent?.()
      }
    },
    [client, sessionId, effectiveCart, onBackendEvent],
  )

  const sendImpression = useCallback(
    async (result: RecommendationResponse, currentCart: number[]) => {
      if (result.recommendations.length === 0) return
      if (impressionSentRef.current === result) return
      impressionSentRef.current = result
      try {
        await client.impression({
          session_id: result.session_id,
          recommendation_ids: result.recommendations.map((r) => r.product_id),
          cart: currentCart,
          model_version: result.model_version,
        })
        onBackendEvent?.()
      } catch {
        // la impresión no bloquea la visualización; el error queda en el log de diagnóstico
      }
    },
    [client, onBackendEvent],
  )

  useEffect(() => {
    if (status === "success" && response && !impressionSentRef.current) {
      void sendImpression(response, effectiveCart)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, response])

  const sendFeedback = useCallback(
    async (productId: number, kind: FeedbackKind): Promise<boolean> => {
      if (!response) return false
      try {
        await client.feedback({
          session_id: response.session_id,
          product_id: productId,
          event: kind,
          recommendation_ids: response.recommendations.map((r) => r.product_id),
        })
        if (kind === "accepted") {
          setAcceptedIds((prev) =>
            prev.includes(productId) ? prev : [...prev, productId],
          )
          setAcceptedNow(productId)
        } else if (kind === "rejected") {
          setRejectedIds((prev) => {
            const next = prev.includes(productId) ? prev : [...prev, productId]
            rejectedRef.current = next
            return next
          })
          setAcceptedNow(null)
        } else {
          setIgnoredIds((prev) =>
            prev.includes(productId) ? prev : [...prev, productId],
          )
        }
        onBackendEvent?.()
        return true
      } catch (err) {
        setError(describeApiError(err))
        onBackendEvent?.()
        return false
      }
    },
    [client, response, onBackendEvent],
  )

  const reset = useCallback(() => {
    setResponse(null)
    setStatus("idle")
    setError(null)
    setAcceptedIds([])
    setRejectedIds([])
    setIgnoredIds([])
    setAcceptedNow(null)
    impressionSentRef.current = null
    hasFetchedRef.current = false
  }, [])

  return {
    status,
    response,
    error,
    acceptedIds,
    rejectedIds,
    ignoredIds,
    acceptedNow,
    fetchRecommendations,
    sendFeedback,
    reset,
  }
}
