import { Badge, Box, Button, Heading, HStack, Text, VStack } from "@chakra-ui/react"
import { LuCircleCheck, LuCircleX, LuFlaskConical } from "react-icons/lu"
import type { BackendStatus } from "../hooks/useHealthPoll"
import { ApiLogTable } from "./ApiLogTable"
import { useApiActivityLog } from "@/shared/api/api-activity-log"

export interface DiagnosticsPanelProps {
  backendState: BackendStatus
  inventory: Record<string, boolean>
  onRunHealthCheck: () => void
}

interface ScenarioInfo {
  id: string
  title: string
  how: string
}

const SCENARIOS: ScenarioInfo[] = [
  {
    id: "T01",
    title: "Recomendación normal",
    how: "Pulsa «Pedir recomendaciones» con el backend activo: se envía POST /v1/recommendations real y se muestran los IDs numéricos que retorne el modelo.",
  },
  {
    id: "T02",
    title: "Aceptación",
    how: "Pulsa «Agregar» en una tarjeta: se envía evento accepted a /v1/events/feedback; la tarjeta se marca verde solo si el backend responde HTTP 202.",
  },
  {
    id: "T03",
    title: "Rechazo",
    how: "Pulsa «No me interesa»: se envía evento rejected real; la tarjeta se marca roja únicamente tras recibir HTTP 202.",
  },
  {
    id: "T04",
    title: "No repetición en la demo",
    how: "Los IDs rechazados se acumulan por sesión y se envían en el campo rejected de la siguiente solicitud real. El filtrado lo hace el backend, no el frontend.",
  },
  {
    id: "T05",
    title: "Un candidato",
    how: "Usa un carrito y un inventario que dejen un solo candidato válido; el backend retornará una única recomendación y se explica en pantalla.",
  },
  {
    id: "T06",
    title: "Sin candidatos",
    how: "Si el backend retorna recommendations: [], se muestra «No hay recomendaciones elegibles para este contexto». No se inventa ninguna recomendación.",
  },
  {
    id: "T07",
    title: "Modelo no cargado o backend degradado",
    how: "El estado /health se consulta cada 15 s. Con model_loaded: false o HTTP 503 se muestra «Backend degradado» con acción de reintento; nunca se presentan recomendaciones como si fueran del modelo.",
  },
  {
    id: "T08",
    title: "Solicitud inválida (HTTP 422)",
    how: "El escenario de solicitud inválida envía k: 99 real a /v1/recommendations; el backend responde 422 y la interfaz muestra el error legible conservando la pantalla estable.",
  },
  {
    id: "T09",
    title: "Carrito vacío",
    how: "Quita todos los productos del carrito: se envía cart: [] real; se muestran las recomendaciones reales, el campo fallback y las advertencias del backend.",
  },
  {
    id: "T10",
    title: "Inventario no disponible",
    how: "El inventario de demo marca 22935 en false; los productos sin inventario se muestran deshabilitados. Si el backend responde fallback, se muestra junto con fallback: true.",
  },
  {
    id: "T11",
    title: "IA no disponible",
    how: "No existe endpoint de IA. Se muestra la nota informativa sin generar explicaciones artificiales ni endpoints inventados.",
  },
  {
    id: "T12",
    title: "Sesión no autorizada",
    how: "Si un proxy responde 401/403, la interfaz muestra el error de autorización. El frontend no agrega autenticación ni simula identidad.",
  },
]

export function DiagnosticsPanel({ backendState, inventory, onRunHealthCheck }: DiagnosticsPanelProps) {
  const { entries, clear } = useApiActivityLog()
  const unavailable = backendState === "unavailable"

  return (
    <Box bg="bg" rounded="xl" borderWidth="1px" borderColor="border" p="5" shadow="sm">
      <VStack align="stretch" gap="4">
        <HStack justify="space-between" flexWrap="wrap" gap="3">
          <HStack gap="2">
            <LuFlaskConical />
            <Heading size="md">Diagnóstico y guía T01–T12</Heading>
          </HStack>
          <HStack gap="2">
            <Button size="xs" variant="outline" onClick={onRunHealthCheck}>
              Verificar /health
            </Button>
            <Button size="xs" variant="ghost" onClick={clear}>
              Limpiar registro
            </Button>
          </HStack>
        </HStack>

        {unavailable && (
          <Text textStyle="sm" color="red.600">
            El backend no está disponible. Inicia uvicorn en la raíz del repositorio y
            recarga; la interfaz no usa datos simulados mientras el backend esté apagado.
          </Text>
        )}

        <VStack align="stretch" gap="2">
          {SCENARIOS.map((scenario) => (
            <Box
              key={scenario.id}
              borderLeftWidth="3px"
              borderLeftColor="blue.500"
              pl="3"
              py="1"
            >
              <HStack gap="2" flexWrap="wrap">
                <Badge colorPalette="blue" variant="subtle">
                  {scenario.id}
                </Badge>
                <Text textStyle="sm" fontWeight="medium">
                  {scenario.title}
                </Text>
              </HStack>
              <Text textStyle="xs" color="fg.muted" mt="0.5">
                {scenario.how}
              </Text>
            </Box>
          ))}
        </VStack>

        <Box>
          <HStack gap="2" mb="2">
            <LuCircleCheck color="var(--chakra-colors-green-500)" />
            <Text textStyle="sm" fontWeight="medium">
              Registro de llamadas reales al backend
            </Text>
          </HStack>
          <ApiLogTable entries={entries} />
        </Box>

        <Box>
          <HStack gap="2">
            <LuCircleX color="var(--chakra-colors-orange-500)" />
            <Text textStyle="sm" fontWeight="medium">
              Inventario de demo
            </Text>
          </HStack>
          <HStack gap="2" mt="1" flexWrap="wrap">
            {Object.entries(inventory).map(([id, available]) => (
              <Badge
                key={id}
                colorPalette={available ? "green" : "red"}
                variant="subtle"
              >
                {id}: {available ? "disponible" : "no disponible"}
              </Badge>
            ))}
          </HStack>
        </Box>
      </VStack>
    </Box>
  )
}
