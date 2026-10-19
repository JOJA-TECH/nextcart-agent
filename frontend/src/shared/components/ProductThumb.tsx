import { Box, Center } from "@chakra-ui/react"
import { LuShoppingBasket } from "react-icons/lu"

export type ProductThumbSize = "xs" | "md" | "lg"

const SIZE_STYLES: Record<ProductThumbSize, number> = {
  xs: 36,
  md: 56,
  lg: 72,
}

/**
 * Placeholder de producto: el dataset Instacart no incluye imágenes, así que
 * la misma canasta de comida representa a todos los productos (sin URLs de
 * imagen ni archivos por producto).
 */
export function ProductThumb({
  size = "md",
  muted = false,
  ariaHidden = true,
}: {
  size?: ProductThumbSize
  /** true → tinte apagado (producto sin inventario o desconocido). */
  muted?: boolean
  ariaHidden?: boolean
}) {
  const px = SIZE_STYLES[size]
  return (
    <Center
      as="span"
      boxSize={`${px}px`}
      rounded="md"
      bg={muted ? "bg.subtle" : "bg.muted"}
      color={muted ? "fg.muted" : "orange.600"}
      flexShrink={0}
      aria-hidden={ariaHidden}
    >
      <LuShoppingBasket
        style={{ width: Math.round(px * 0.5), height: Math.round(px * 0.5) }}
      />
    </Center>
  )
}

/** Avatar numérico para IDs sin entrada en el catálogo. */
export function ProductFallbackThumb({
  label,
  boxSize = 36,
}: {
  label: string
  boxSize?: number
}) {
  return (
    <Box
      as="span"
      boxSize={`${boxSize}px`}
      rounded="md"
      bg="bg.subtle"
      color="fg.muted"
      display="inline-flex"
      alignItems="center"
      justifyContent="center"
      flexShrink={0}
    >
      <Box as="span" fontSize="2xs" fontWeight="medium">
        {label}
      </Box>
    </Box>
  )
}
