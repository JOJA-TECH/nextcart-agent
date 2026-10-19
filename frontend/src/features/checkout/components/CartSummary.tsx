import {
  Button,
  HStack,
  Heading,
  Separator,
  Text,
  VStack,
} from "@chakra-ui/react"
import { LuTrash2 } from "react-icons/lu"
import type { NextCartClient } from "@/shared/api/contracts"
import { ProductFallbackThumb, ProductThumb } from "@/shared/components/ProductThumb"
import {
  useCatalogCacheSnapshot,
  useCatalogProduct,
} from "@/features/catalog/catalogStore"
import { PLACEHOLDER_IMAGE_NOTE } from "@/shared/catalog/catalog-notes"
import { formatCurrency } from "@/shared/utils/format"

export interface CartSummaryProps {
  client: NextCartClient
  cart: number[]
  onRemove: (productId: number) => void
}

function CartItemRow({
  client,
  id,
  onRemove,
}: {
  client: NextCartClient
  id: number
  onRemove: (productId: number) => void
}) {
  const { product } = useCatalogProduct(client, id)
  const name = product?.product_name ?? `Producto #${id}`
  return (
    <HStack justify="space-between" gap="3">
      <HStack gap="3" minW="0">
        {product ? (
          <ProductThumb size="xs" />
        ) : (
          <ProductFallbackThumb label={String(id).slice(-2)} />
        )}
        <VStack gap="0" align="start" minW="0">
          <Text textStyle="sm" truncate>
            {name}
          </Text>
          <Text textStyle="xs" color="fg.muted">
            ID {id}
            {product
              ? ` · ${formatCurrency(product.price, product.currency)}`
              : " · consultando…"}
          </Text>
        </VStack>
      </HStack>
      <Button
        size="2xs"
        variant="ghost"
        color="fg.muted"
        aria-label={`Quitar producto ${id} del carrito`}
        onClick={() => onRemove(id)}
      >
        <LuTrash2 />
      </Button>
    </HStack>
  )
}

export function CartSummary({ client, cart, onRemove }: CartSummaryProps) {
  const cache = useCatalogCacheSnapshot()
  // Total con los precios resueltos del catálogo real; los pendientes no
  // cuentan hasta que llegue su precio.
  const resolved = cart.filter((id) => cache.has(id))
  const total = resolved.reduce(
    (sum, id) => sum + (cache.get(id)?.price ?? 0),
    0,
  )

  return (
    <VStack align="stretch" gap="4">
      <Heading size="md">Resumen del carrito</Heading>

      {cart.length === 0 ? (
        <Text textStyle="sm" color="fg.muted">
          El carrito está vacío (T09). Se enviará{" "}
          <Text as="span" fontFamily="mono">cart: []</Text> real al backend.
        </Text>
      ) : (
        <VStack align="stretch" gap="2">
          {cart.map((id) => (
            <CartItemRow key={id} client={client} id={id} onRemove={onRemove} />
          ))}
        </VStack>
      )}

      <Separator />

      <HStack justify="space-between">
        <Text textStyle="sm" color="fg.muted">
          Total ({resolved.length} de {cart.length} producto
          {cart.length === 1 ? "" : "s"} con precio)
        </Text>
        <Text fontWeight="bold">{formatCurrency(total, "COP")}</Text>
      </HStack>

      <Separator />

      <Text textStyle="2xs" color="fg.subtle">
        Nombres y precios provienen del catálogo del dataset servido por
        /v1/catalog. {PLACEHOLDER_IMAGE_NOTE}
      </Text>

      <Text textStyle="xs" color="fg.muted">
        Usa el «Catálogo del dataset» para agregar productos reales de
        Instacart al carrito.
      </Text>
    </VStack>
  )
}
