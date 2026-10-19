import { useCallback, useEffect, useState } from "react"
import {
  Box,
  Heading,
  HStack,
  SimpleGrid,
  Stack,
  Text,
  VStack,
} from "@chakra-ui/react"
import type { MetricsSummary, NextCartClient } from "@/shared/api/contracts"
import { describeApiError } from "@/shared/api/api-activity-log"
import { formatMs, formatPercent } from "@/shared/utils/format"

export interface MetricsSummaryPanelProps {
  client: NextCartClient
  refreshNonce: number
}

interface MetricCardProps {
  label: string
  value: string
  tone?: "default" | "success" | "warning" | "danger"
}

function MetricCard({ label, value, tone = "default" }: MetricCardProps) {
  const color =
    tone === "success"
      ? "green.600"
      : tone === "warning"
        ? "orange.600"
        : tone === "danger"
          ? "red.600"
          : "fg"
  return (
    <Stack bg="bg.subtle" rounded="lg" p="3" gap="0">
      <Text textStyle="2xs" color="fg.muted" textTransform="uppercase" letterSpacing="wide">
        {label}
      </Text>
      <Text fontWeight="bold" textStyle="md" color={color}>
        {value}
      </Text>
    </Stack>
  )
}

export function MetricsSummaryPanel({ client, refreshNonce }: MetricsSummaryPanelProps) {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await client.metricsSummary()
      setMetrics(data)
      setError(null)
    } catch (err) {
      setError(describeApiError(err))
    }
  }, [client])

  useEffect(() => {
    void load()
  }, [load, refreshNonce])

  return (
    <Box bg="bg" rounded="xl" borderWidth="1px" borderColor="border" p="5" shadow="sm">
      <VStack align="stretch" gap="3">
        <Heading size="md">Métricas observadas</Heading>

        {error && (
          <Text textStyle="sm" color="red.600">
            {error}
          </Text>
        )}

        {!error && !metrics && (
          <Text textStyle="sm" color="fg.muted">
            Esperando datos de /v1/metrics/summary…
          </Text>
        )}

        {metrics && (
          <>
            <SimpleGrid columns={2} gap="2">
              <MetricCard label="Impresiones" value={String(metrics.impressions)} />
              <MetricCard label="Aceptadas" value={String(metrics.accepted)} tone="success" />
              <MetricCard label="Rechazadas" value={String(metrics.rejected)} tone="danger" />
              <MetricCard label="Ignoradas" value={String(metrics.ignored)} />
              <MetricCard
                label="Tasa de aceptación"
                value={
                  metrics.acceptance_rate_observed == null
                    ? "—"
                    : formatPercent(metrics.acceptance_rate_observed)
                }
                tone="success"
              />
              <MetricCard
                label="Cobertura de catálogo"
                value={formatPercent(metrics.catalog_coverage_observed)}
              />
              <MetricCard label="Latencia media" value={formatMs(metrics.latency_mean_ms)} />
              <MetricCard label="Latencia p95" value={formatMs(metrics.latency_p95_ms)} />
              <MetricCard
                label="Errores"
                value={String(metrics.errors)}
                tone={metrics.errors > 0 ? "danger" : "default"}
              />
              <MetricCard label="Versión del modelo" value={metrics.model_version ?? "—"} />
            </SimpleGrid>
            <Box bg="orange.subtle" rounded="md" px="3" py="2">
              <Text textStyle="2xs" color="orange.700">
                {metrics.disclaimer}
              </Text>
            </Box>
          </>
        )}

        <HStack />
      </VStack>
    </Box>
  )
}
