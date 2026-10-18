import {
  Button,
  HStack,
  Heading,
  Image,
  Separator,
  Text,
  VStack,
} from "@chakra-ui/react"
import { LuTrash2 } from "react-icons/lu"
import { LuPlus } from "react-icons/lu"
import { CATALOG_DEMO_TAG, demoCatalog, lookupDemoProduct } from "@/shared/catalog-demo"
import { formatCurrency } from "@/shared/utils/format"

export interface CartSummaryProps {
  cart: number[]
  onRemove: (productId: number) => void
  onAddProduct: (productId: number) => void
}

export function CartSummary({ cart, onRemove, onAddProduct }: CartSummaryProps) {
  const total = cart.reduce((sum, id) => sum + lookupDemoProduct(id).price, 0)

  const candidates = Object.values(demoCatalog).filter(
    (entry) => !cart.includes(entry.id),
  )

  return (
    <VStack align="stretch" gap="4">
      <Heading size="md">Resumen del carrito</Heading>

      {cart.length === 0 ? (
        <Text textStyle="sm" color="fg.muted">
          El carrito está vacío (T09). Se enviará <Text as="span" fontFamily="mono">cart: []</Text> real al backend.
        </Text>
      ) : (
        <VStack align="stretch" gap="2">
          {cart.map((id) => {
            const product = lookupDemoProduct(id)
            return (
              <HStack key={id} justify="space-between" gap="3">
                <HStack gap="3" minW="0">
                  {product.image ? (
                    <Image
                      src={product.image}
                      alt={product.name}
                      boxSize="9"
                      rounded="sm"
                      objectFit="cover"
                      bg="bg.muted"
                      flexShrink={0}
                    />
                  ) : (
                    <VStack
                      boxSize="9"
                      rounded="sm"
                      bg="bg.muted"
                      align="center"
                      justify="center"
                      flexShrink={0}
                    >
                      <Text textStyle="2xs" color="fg.muted">
                        {id}
                      </Text>
                    </VStack>
                  )}
                  <VStack gap="0" align="start" minW="0">
                    <Text textStyle="sm" truncate>
                      {product.name}
                    </Text>
                    <Text textStyle="xs" color="fg.muted">
                      ID {id} · {formatCurrency(product.price, product.currency)}
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
          })}
        </VStack>
      )}

      <Separator />

      <HStack justify="space-between">
        <Text textStyle="sm" color="fg.muted">
          Total de demo ({cart.length} producto{cart.length === 1 ? "" : "s"})
        </Text>
        <Text fontWeight="bold">{formatCurrency(total, "COP")}</Text>
      </HStack>
      <Text textStyle="2xs" color="fg.subtle">
        Totales calculados sobre precios {CATALOG_DEMO_TAG}; no son datos reales del dataset.
      </Text>

      <Separator />

      <VStack align="stretch" gap="2">
        <Text textStyle="sm" fontWeight="medium">
          Agregar producto de demo
        </Text>
        <HStack gap="2" flexWrap="wrap">
          {candidates.map((entry) => (
            <Button
              key={entry.id}
              size="2xs"
              variant="outline"
              onClick={() => onAddProduct(entry.id)}
            >
              <LuPlus />
              {entry.name} ({entry.id})
            </Button>
          ))}
        </HStack>
      </VStack>
    </VStack>
  )
}
