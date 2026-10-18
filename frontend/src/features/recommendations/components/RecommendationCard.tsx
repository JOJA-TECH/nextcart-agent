import { Badge, Button, Card, HStack, Stack, Text } from "@chakra-ui/react"
import { LuMinus, LuShoppingCart, LuTrash2 } from "react-icons/lu"
import type { NextCartClient } from "@/shared/api/contracts"
import { ProductFallbackThumb, ProductThumb } from "@/shared/components/ProductThumb"
import { useCatalogProduct } from "@/features/catalog/catalogStore"
import { formatCurrency } from "@/shared/utils/format"

export interface RecommendationCardProps {
  client: NextCartClient
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
    client,
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

  // Nombre/precio/categoría del catálogo real (/v1/catalog, dataset Instacart).
  const { product } = useCatalogProduct(client, productId)
  const name = product?.product_name ?? `Producto #${productId}`
  const category = product?.aisle ?? product?.department ?? null
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
          {product ? (
            <ProductThumb size="md" muted={unavailable} />
          ) : (
            <ProductFallbackThumb label={String(productId).slice(-2)} boxSize={56} />
          )}
          <Stack gap="0.5" minW="0">
            <Text fontWeight="medium" lineClamp={2}>
              {name}
            </Text>
            <Text textStyle="xs" color="fg.muted" minW="0">
              ID {productId}
              {category ? ` · ${category}` : ""}
              {product
                ? ` · ${formatCurrency(product.price, product.currency)}`
                : ""}
            </Text>
            <Badge colorPalette="blue" variant="subtle" alignSelf="flex-start">
              catálogo Instacart
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
            aria-label={`Agregar ${name} al carrito`}
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
            aria-label={`No me interesa ${name}`}
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
            aria-label={`Registrar ${name} como ignorada`}
          >
            <LuMinus />
            Registrar ignorada
          </Button>
        </HStack>
      </Card.Body>
    </Card.Root>
  )
}
