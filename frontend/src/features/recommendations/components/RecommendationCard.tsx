import { Badge, Button, Card, HStack, Image, Stack, Text } from "@chakra-ui/react"
import { LuMinus, LuShoppingCart, LuTrash2 } from "react-icons/lu"
import { CATALOG_DEMO_TAG, lookupDemoProduct } from "@/shared/catalog-demo"
import { formatCurrency } from "@/shared/utils/format"

export interface RecommendationCardProps {
  productId: number
  score: number
  reason: string
  source: string
  inventoryAvailable: boolean
  accepted: boolean
  rejected: boolean
  ignored: boolean
  busy: boolean
  onAccept: () => void
  onReject: () => void
  onIgnore: () => void
}

export function RecommendationCard(props: RecommendationCardProps) {
  const {
    productId,
    score,
    reason,
    source,
    inventoryAvailable,
    accepted,
    rejected,
    ignored,
    busy,
    onAccept,
    onReject,
    onIgnore,
  } = props

  const product = lookupDemoProduct(productId)
  const unavailable = !inventoryAvailable
  // Un solo voto por producto: evita los badges aceptado+rechazado a la vez.
  const voted = accepted || rejected || ignored

  return (
    <Card.Root
      size="sm"
      opacity={unavailable ? 0.6 : 1}
      borderColor={accepted ? "green.emphasized" : "border"}
    >
      <Card.Body gap="3" minW={{ base: "full", sm: "56" }}>
        <HStack align="start" gap="3">
          {product.image ? (
            <Image
              src={product.image}
              alt={product.name}
              boxSize="14"
              rounded="md"
              objectFit="cover"
              bg="bg.muted"
              flexShrink={0}
            />
          ) : (
            <Stack
              boxSize="14"
              rounded="md"
              bg="bg.muted"
              align="center"
              justify="center"
              flexShrink={0}
            >
              <Text textStyle="lg" fontWeight="bold" color="fg.muted">
                {String(productId).slice(-2)}
              </Text>
            </Stack>
          )}
          <Stack gap="0.5" minW="0">
            <Text fontWeight="medium" lineClamp={2}>
              {product.name}
            </Text>
            <Text textStyle="xs" color="fg.muted">
              ID {productId} · {product.category} · {formatCurrency(product.price, product.currency)}
            </Text>
            <Badge colorPalette="purple" variant="subtle" alignSelf="flex-start">
              {CATALOG_DEMO_TAG}
            </Badge>
          </Stack>
        </HStack>

        <Stack gap="1">
          <Text textStyle="xs" color="fg.muted">
            {reason}
          </Text>
          <HStack gap="2" flexWrap="wrap">
            <Text textStyle="xs" color="fg.subtle">
              score {score.toFixed(4)}
            </Text>
            <Text textStyle="xs" color="fg.subtle">
              · {source}
            </Text>
            {unavailable && (
              <Badge colorPalette="red" variant="subtle">sin inventario</Badge>
            )}
            {accepted && (
              <Badge colorPalette="green" variant="subtle">aceptado</Badge>
            )}
            {rejected && (
              <Badge colorPalette="red" variant="subtle">rechazado</Badge>
            )}
            {ignored && (
              <Badge colorPalette="gray" variant="subtle">ignorado</Badge>
            )}
          </HStack>
        </Stack>

        <HStack gap="2" flexWrap="wrap">
          <Button
            size="xs"
            colorPalette="green"
            onClick={onAccept}
            loading={busy}
            disabled={unavailable || voted}
            aria-label={`Agregar ${product.name} al carrito`}
          >
            <LuShoppingCart />
            Agregar
          </Button>
          <Button
            size="xs"
            colorPalette="red"
            variant="outline"
            onClick={onReject}
            disabled={busy || voted}
            aria-label={`No me interesa ${product.name}`}
          >
            <LuTrash2 />
            No me interesa
          </Button>
          <Button
            size="xs"
            variant="ghost"
            color="fg.muted"
            onClick={onIgnore}
            disabled={busy || voted}
            aria-label={`Registrar ${product.name} como ignorada`}
          >
            <LuMinus />
            Registrar ignorada
          </Button>
        </HStack>
      </Card.Body>
    </Card.Root>
  )
}
