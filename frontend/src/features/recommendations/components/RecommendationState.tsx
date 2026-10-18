import { LoadingState, EmptyState, ErrorState } from "@/shared/components/States"
import type { RequestStatus } from "../hooks/useRecommendations"
import { RecommendationList } from "./RecommendationList"
import type { Recommendation } from "@/shared/api/contracts"
import { Alert } from "@chakra-ui/react"

export interface RecommendationStateProps {
  status: RequestStatus
  error: string | null
  recommendations: Recommendation[]
  inventory: Record<string, boolean>
  acceptedIds: number[]
  rejectedIds: number[]
  ignoredIds: number[]
  busyProductId: number | null
  onAccept: (productId: number) => void
  onReject: (productId: number) => void
  onIgnore: (productId: number) => void
}

export function RecommendationState(props: RecommendationStateProps) {
  const {
    status,
    error,
    recommendations,
    inventory,
    acceptedIds,
    rejectedIds,
    ignoredIds,
    busyProductId,
    onAccept,
    onReject,
    onIgnore,
  } = props

  if (status === "loading") return <LoadingState title="Consultando recomendaciones reales del backend…" />
  if (status === "error" && error) {
    return <ErrorState title="Error del backend" description={error} />
  }
  if (status !== "success") {
    return (
      <EmptyState
        title="Sin recomendaciones todavía"
        description="Presiona «Pedir recomendaciones» para consultar el modelo local servido por FastAPI."
      />
    )
  }
  // T06: el backend retornó recommendations: [] — no se inventa nada.
  if (recommendations.length === 0) {
    return (
      <EmptyState
        title="No hay recomendaciones elegibles para este contexto"
        description="El backend no retornó candidatos para este carrito e inventario."
      />
    )
  }

  return (
    <RecommendationList
      recommendations={recommendations}
      inventory={inventory}
      acceptedIds={acceptedIds}
      rejectedIds={rejectedIds}
      ignoredIds={ignoredIds}
      busyProductId={busyProductId}
      onAccept={onAccept}
      onReject={onReject}
      onIgnore={onIgnore}
    />
  )
}

export function FeedbackErrorAlert({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <Alert.Root status="error" variant="subtle" mt="3">
      <Alert.Indicator />
      <Alert.Title>{message}</Alert.Title>
    </Alert.Root>
  )
}
