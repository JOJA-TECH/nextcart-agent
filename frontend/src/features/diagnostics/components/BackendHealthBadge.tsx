import { Badge, HStack, Icon, Text } from "@chakra-ui/react"
import { LuCircleCheck, LuTriangleAlert, LuBan } from "react-icons/lu"

export type BackendStatus = "connected" | "degraded" | "unavailable"

export interface BackendHealthBadgeProps {
  state: BackendStatus
  detail?: string
}

export function BackendHealthBadge({ state, detail }: BackendHealthBadgeProps) {
  if (state === "connected") {
    return (
      <HStack gap="2">
        <Badge colorPalette="green" variant="subtle" gap="1" px="2">
          <Icon as={LuCircleCheck} />
          Backend FastAPI conectado
        </Badge>
        {detail && (
          <Text textStyle="xs" color="fg.muted">
            {detail}
          </Text>
        )}
      </HStack>
    )
  }
  if (state === "degraded") {
    return (
      <HStack gap="2">
        <Badge colorPalette="orange" variant="subtle" gap="1" px="2">
          <Icon as={LuTriangleAlert} />
          Backend degradado
        </Badge>
        {detail && (
          <Text textStyle="xs" color="fg.muted">
            {detail}
          </Text>
        )}
      </HStack>
    )
  }
  return (
    <HStack gap="2">
      <Badge colorPalette="red" variant="subtle" gap="1" px="2">
        <Icon as={LuBan} />
        Backend no disponible
      </Badge>
      {detail && (
        <Text textStyle="xs" color="fg.muted">
          {detail}
        </Text>
      )}
    </HStack>
  )
}
