import { useState } from "react"
import {
  Badge,
  Box,
  Button,
  HStack,
  Heading,
  Separator,
  Text,
  VStack,
  Alert,
} from "@chakra-ui/react"
import { LuRefreshCw, LuSparkles } from "react-icons/lu"
import { NO_AI_NOTE } from "@/shared/ai/no-ai"
import { DEMO_DATA_NOTE } from "@/shared/catalog-demo"
import type {
  RecommendationResponse,
} from "@/shared/api/contracts"
import type { UseRecommendationsResult } from "../hooks/useRecommendations"
import { RecommendationState, FeedbackErrorAlert } from "./RecommendationState"

export interface RecommendationWidgetProps {
  session: UseRecommendationsResult
  inventory: Record<string, boolean>
  inventoryOverride: Record<string, boolean> | null
  onRetry: () => void
  onInvalidRequest: () => void
}

function backendBadge(response: RecommendationResponse) {
  return (
    <HStack gap="2" flexWrap="wrap">
      {response.fallback && (
        <Badge colorPalette="amber" variant="subtle">
          fallback: {String(response.fallback)}
        </Badge>
      )}
      {response.model_version && (
        <Badge colorPalette="blue" variant="subtle">
          modelo {response.model_version}
        </Badge>
      )}
      <Badge colorPalette="gray" variant="subtle">
        {response.latency_ms.toFixed(2)} ms
      </Badge>
    </HStack>
  )
}

export function RecommendationWidget({
  session,
  inventory,
  inventoryOverride,
  onRetry,
  onInvalidRequest,
}: RecommendationWidgetProps) {
  const [busyProductId, setBusyProductId] = useState<number | null>(null)
  const handleAccept = async (productId: number) => {
    setBusyProductId(productId)
    const ok = await session.sendFeedback(productId, "accepted")
    setBusyProductId(null)
    void ok
  }

  const handleReject = async (productId: number) => {
    setBusyProductId(productId)
    const ok = await session.sendFeedback(productId, "rejected")
    setBusyProductId(null)
    void ok
  }

  const handleIgnore = async (productId: number) => {
    setBusyProductId(productId)
    const ok = await session.sendFeedback(productId, "ignored")
    setBusyProductId(null)
    void ok
  }

  const requestRecommendations = () => {
    void session.fetchRecommendations({
      inventoryOverride: inventoryOverride ?? undefined,
    })
  }

  const warnings = session.response?.warnings ?? []

  return (
    <Box bg="bg" rounded="xl" borderWidth="1px" borderColor="border" p="5" shadow="sm">
      <VStack align="stretch" gap="4">
        <HStack justify="space-between" flexWrap="wrap" gap="3">
          <HStack gap="2">
            <LuSparkles color="var(--chakra-colors-blue-600)" />
            <Heading size="md">Recomendaciones de NEXTCART</Heading>
          </HStack>
          <HStack gap="2">
            {session.response && backendBadge(session.response)}
            <Button
              size="sm"
              colorPalette="blue"
              onClick={requestRecommendations}
              loading={session.status === "loading"}
            >
              <LuRefreshCw />
              Pedir recomendaciones
            </Button>
            <Button size="sm" variant="outline" colorPalette="red" onClick={onInvalidRequest}>
              Probar solicitud inválida (T08)
            </Button>
          </HStack>
        </HStack>

        <Text textStyle="xs" color="fg.muted">
          {DEMO_DATA_NOTE}
        </Text>

        {warnings.length > 0 && (
          <Alert.Root status="warning" variant="subtle">
            <Alert.Indicator />
            <Alert.Title>Advertencias del backend: {warnings.join(" · ")}</Alert.Title>
          </Alert.Root>
        )}

        {session.acceptedNow != null && (
          <Alert.Root status="success" variant="subtle">
            <Alert.Indicator />
            <Alert.Title>
              Producto {session.acceptedNow} aceptado — evento «accepted» confirmado por el backend (HTTP 202).
            </Alert.Title>
          </Alert.Root>
        )}

        <FeedbackErrorAlert message={session.error} />

        <Separator />

        <RecommendationState
          status={session.status}
          error={session.error}
          recommendations={session.response?.recommendations ?? []}
          inventory={inventoryOverride ?? inventory}
          acceptedIds={session.acceptedIds}
          rejectedIds={session.rejectedIds}
          ignoredIds={session.ignoredIds}
          busyProductId={busyProductId}
          onAccept={handleAccept}
          onReject={handleReject}
          onIgnore={handleIgnore}
        />

        <Text textStyle="xs" color="fg.subtle">
          {NO_AI_NOTE}
        </Text>

        <Button size="xs" variant="ghost" alignSelf="flex-start" onClick={onRetry}>
          Reintentar conexión con el backend
        </Button>
      </VStack>
    </Box>
  )
}
