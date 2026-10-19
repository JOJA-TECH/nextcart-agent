import { HStack, Image, Text, Box } from "@chakra-ui/react"
import type { BackendStatus } from "@/features/diagnostics/components/BackendHealthBadge"
import { BackendHealthBadge } from "@/features/diagnostics/components/BackendHealthBadge"

export interface CheckoutHeaderProps {
  backendState: BackendStatus
  backendDetail?: string
  modelVersion: string | null
}

export function CheckoutHeader({ backendState, backendDetail, modelVersion }: CheckoutHeaderProps) {
  return (
    <Box bg="blue.900" color="white" px={{ base: "4", lg: "8" }} py="4">
      <HStack justify="space-between" flexWrap="wrap" gap="3">
        <HStack gap="3">
          <Image src="/favicon.svg" alt="NEXTCART" boxSize="8" />
          <Text fontWeight="bold" textStyle="lg" letterSpacing="tight">
            NEXTCART
          </Text>
          <Text textStyle="sm" color="blue.200" hideBelow="md">
            Checkout asistido por recomendaciones
          </Text>
        </HStack>
        <BackendHealthBadge
          state={backendState}
          detail={
            backendDetail ??
            (modelVersion ? `modelo ${modelVersion}` : undefined)
          }
        />
      </HStack>
    </Box>
  )
}
