import { useCallback, useEffect, useMemo, useState } from "react"
import { Alert, Box, Grid, HStack, Heading, Text, VStack } from "@chakra-ui/react"
import type { NextCartClient } from "@/shared/api/contracts"
import { CartSummary } from "./CartSummary"
import { CheckoutHeader } from "./CheckoutHeader"
import { RecommendationWidget } from "@/features/recommendations/components/RecommendationWidget"
import { useRecommendations } from "@/features/recommendations/hooks/useRecommendations"
import { MetricsSummaryPanel } from "@/features/diagnostics/components/MetricsSummaryPanel"
import { DEMO_DATA_NOTE } from "@/shared/catalog-demo"
import { NO_AI_NOTE } from "@/shared/ai/no-ai"
import { DiagnosticsPanel } from "@/features/diagnostics/components/DiagnosticsPanel"
import { useHealthPoll } from "@/features/diagnostics/hooks/useHealthPoll"

export interface CheckoutPageProps {
  client: NextCartClient
}

export const BASE_INVENTORY: Record<string, boolean> = {
  "21137": true,
  "22935": false,
}

export function CheckoutPage({ client }: CheckoutPageProps) {
  const [cart, setCart] = useState<number[]>([24852, 13176])
  const [sessionId] = useState(() => `sess-${Math.random().toString(36).slice(2, 8)}`)
  const { health, state, detail, refresh: refreshHealth } = useHealthPoll(client)
  const [metricsNonce, setMetricsNonce] = useState(0)

  const onBackendEvent = useCallback(() => setMetricsNonce((n) => n + 1), [])

  const recommendations = useRecommendations(client, sessionId, cart, onBackendEvent)

  useEffect(() => {
    void refreshHealth()
  }, [refreshHealth])

  const healthError = health.kind === "error" ? health.error : null

  const inventoryOverride = useMemo<Record<string, boolean> | null>(() => {
    if (recommendations.status !== "success" || !recommendations.response) return null
    const inv: Record<string, boolean> = {}
    for (const rec of recommendations.response.recommendations) {
      inv[String(rec.product_id)] = BASE_INVENTORY[String(rec.product_id)] ?? true
    }
    return inv
  }, [recommendations.status, recommendations.response])

  const addToCart = (productId: number) =>
    setCart((prev) => (prev.includes(productId) ? prev : [...prev, productId]))
  const removeFromCart = (productId: number) =>
    setCart((prev) => prev.filter((id) => id !== productId))

  return (
    <Box minH="100vh" bg="bg.subtle">
      <CheckoutHeader
        backendState={state}
        backendDetail={detail}
        modelVersion={health.kind === "ok" ? (health.data.model_version ?? null) : null}
      />

      <Box px={{ base: "4", lg: "8" }} py="6" maxW="7xl" mx="auto">
        <VStack align="stretch" gap="5">
          {state === "unavailable" && healthError && (
            <Alert.Root status="error" variant="subtle">
              <Alert.Indicator />
              <Alert.Title>{healthError}</Alert.Title>
            </Alert.Root>
          )}

          <HStack justify="space-between" flexWrap="wrap" gap="3">
            <Heading size="lg">Checkout de demostración</Heading>
            <Text textStyle="sm" color="fg.muted">
              Sesión: <Text as="span" fontFamily="mono">{sessionId}</Text>
            </Text>
          </HStack>

          <Text textStyle="xs" color="fg.muted">
            {DEMO_DATA_NOTE}
          </Text>

          <Grid
            templateColumns={{ base: "1fr", lg: "2fr 1fr" }}
            gap="5"
            alignItems="start"
          >
            <VStack align="stretch" gap="5">
              <RecommendationWidget
                session={recommendations}
                inventory={BASE_INVENTORY}
                inventoryOverride={inventoryOverride}
                onRetry={() => {
                  void refreshHealth()
                  onBackendEvent()
                }}
                onInvalidRequest={() => {
                  void recommendations.fetchRecommendations({ invalidRequest: true })
                }}
              />

              <Box display={{ base: "block", lg: "none" }}>
                <MetricsSummaryPanel client={client} refreshNonce={metricsNonce} />
              </Box>
            </VStack>

            <VStack align="stretch" gap="5">
              <Box bg="bg" rounded="xl" borderWidth="1px" borderColor="border" p="5" shadow="sm">
                <CartSummary
                  cart={cart}
                  onRemove={removeFromCart}
                  onAddProduct={addToCart}
                />
              </Box>

              <Box display={{ base: "none", lg: "block" }}>
                <MetricsSummaryPanel client={client} refreshNonce={metricsNonce} />
              </Box>
            </VStack>
          </Grid>

          <DiagnosticsPanel
            backendState={state}
            inventory={BASE_INVENTORY}
            onRunHealthCheck={() => {
              void refreshHealth()
              onBackendEvent()
            }}
          />

          <Text textStyle="2xs" color="fg.subtle" textAlign="center" pb="6">
            {NO_AI_NOTE}
          </Text>
        </VStack>
      </Box>
    </Box>
  )
}
