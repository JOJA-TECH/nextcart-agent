import { useEffect, useMemo, useState } from "react"
import {
  Badge,
  Button,
  Field,
  HStack,
  Input,
  NativeSelect,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react"
import { LuPlus } from "react-icons/lu"
import type { CatalogProduct, NextCartClient } from "@/shared/api/contracts"
import { ProductThumb } from "@/shared/components/ProductThumb"
import { formatCurrency } from "@/shared/utils/format"
import {
  useCatalogAisles,
  useCatalogDepartments,
  useCatalogList,
} from "@/features/catalog/catalogStore"

const PAGE_SIZE = 12

/** Fila del catálogo con botón de agregar al carrito. */
function CatalogRow({
  product,
  inCart,
  busy,
  onAdd,
}: {
  product: CatalogProduct
  inCart: boolean
  busy: boolean
  onAdd: (productId: number) => void
}) {
  return (
    <HStack
      justify="space-between"
      align="start"
      gap="3"
      borderWidth="1px"
      borderColor="border"
      rounded="md"
      p="3"
    >
      <HStack gap="3" minW="0">
        <ProductThumb size="md" />
        <VStack gap="0.5" align="start" minW="0">
          <Text fontWeight="medium" lineClamp={2}>
            {product.product_name}
          </Text>
          <Text textStyle="xs" color="fg.muted" lineClamp={1}>
            ID {product.product_id} · {product.department ?? "—"} ·{" "}
            {product.aisle ?? "—"}
          </Text>
          <Text textStyle="sm" fontWeight="bold">
            {formatCurrency(product.price, product.currency)}
          </Text>
        </VStack>
      </HStack>
      <Button
        size="xs"
        variant={inCart ? "solid" : "outline"}
        colorPalette="green"
        onClick={() => onAdd(product.product_id)}
        disabled={inCart || busy}
        aria-label={`Agregar ${product.product_name} al carrito`}
      >
        <LuPlus />
        {inCart ? "En carrito" : "Agregar"}
      </Button>
    </HStack>
  )
}

export interface CatalogBrowserProps {
  client: NextCartClient
  cart: number[]
  onAddProduct: (productId: number) => void
}

export function CatalogBrowser({
  client,
  cart,
  onAddProduct,
}: CatalogBrowserProps) {
  const [searchInput, setSearchInput] = useState("")
  const [search, setSearch] = useState("")
  const [departmentId, setDepartmentId] = useState<number | null>(null)
  const [aisleId, setAisleId] = useState<number | null>(null)
  const [offset, setOffset] = useState(0)
  const [pendingAdd, setPendingAdd] = useState<number | null>(null)

  // Debounce de la búsqueda: evita pedir al backend por cada tecla.
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput.trim())
      setOffset(0)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput])

  const departments = useCatalogDepartments(client)
  const aisles = useCatalogAisles(client, departmentId)

  const query = useMemo(
    () => ({
      search,
      department_id: departmentId ?? undefined,
      aisle_id: aisleId ?? undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    [search, departmentId, aisleId, offset],
  )
  // useCatalogList devuelve la entrada {data, error, loading}; page = data.
  const { data: page, error, loading } = useCatalogList(client, query)

  const cartSet = useMemo(() => new Set(cart), [cart])
  const busy = pendingAdd !== null

  const onAdd = (productId: number) => {
    setPendingAdd(productId)
    onAddProduct(productId)
    setTimeout(() => setPendingAdd(null), 150)
  }

  const onDepartmentChange = (value: string) => {
    const next = value === "" ? null : Number(value)
    setDepartmentId(next)
    setAisleId(null)
    setOffset(0)
  }

  const onAisleChange = (value: string) => {
    setAisleId(value === "" ? null : Number(value))
    setOffset(0)
  }

  return (
    <VStack align="stretch" gap="4" data-testid="catalog-browser">
      <VStack align="stretch" gap="1">
        <HStack justify="space-between" gap="2" align="baseline">
          <Text fontSize="md" fontWeight="semibold">
            Catálogo del dataset
          </Text>
          {page && (
            <Badge variant="subtle" colorPalette="gray">
              {page.total.toLocaleString("es-CO")} productos
            </Badge>
          )}
        </HStack>
        <Text textStyle="xs" color="fg.muted">
          49.688 productos de Instacart servidos por /v1/catalog (SQLite). Sin
          imágenes en el dataset: se usa un placeholder de canasta.
        </Text>
      </VStack>

      <HStack gap="2" align="end" flexWrap="wrap">
        <Field.Root maxW="sm" minW={{ base: "full", sm: "56" }} flex="1">
          <Field.Label textStyle="xs">Buscar producto</Field.Label>
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="p. ej. bananas, leche, queso"
            aria-label="Buscar producto en el catálogo"
          />
        </Field.Root>
          <Field.Root maxW={{ base: "full", sm: "44" }}>
            <Field.Label textStyle="xs">Departamento</Field.Label>
            <NativeSelect.Root
              size="sm"
            >
              <NativeSelect.Field
                aria-label="Filtrar por departamento"
                value={departmentId === null ? "" : String(departmentId)}
                onChange={(e) => onDepartmentChange(e.currentTarget.value)}
            >
              <option value="">Todos</option>
              {(departments.data ?? []).map((d) => (
                <option key={d.department_id} value={d.department_id}>
                  {d.department} ({d.product_count})
                </option>
              ))}
            </NativeSelect.Field>
            <NativeSelect.Indicator />
          </NativeSelect.Root>
        </Field.Root>
          <Field.Root maxW={{ base: "full", sm: "44" }}>
            <Field.Label textStyle="xs">Pasillo</Field.Label>
            <NativeSelect.Root
              size="sm"
              disabled={departmentId === null}
            >
              <NativeSelect.Field
                aria-label="Filtrar por pasillo"
                value={aisleId === null ? "" : String(aisleId)}
                onChange={(e) => onAisleChange(e.currentTarget.value)}
            >
              <option value="">Todos</option>
              {(aisles.data ?? []).map((a) => (
                <option key={a.aisle_id} value={a.aisle_id}>
                  {a.aisle} ({a.product_count})
                </option>
              ))}
            </NativeSelect.Field>
            <NativeSelect.Indicator />
          </NativeSelect.Root>
        </Field.Root>
      </HStack>

      {error && (
        <Badge colorPalette="red" variant="subtle" alignSelf="flex-start">
          Catálogo no disponible: {error}
        </Badge>
      )}

      {loading && (
        <HStack gap="2">
          <Spinner size="sm" />
          <Text textStyle="xs" color="fg.muted">
            Cargando productos…
          </Text>
        </HStack>
      )}

      {!loading && page && page.items.length === 0 && (
        <Text textStyle="sm" color="fg.muted">
          Sin resultados para “{search || "el filtro actual"}”.
        </Text>
      )}

      {!loading && page && page.items.length > 0 && (
        <VStack align="stretch" gap="2">
          {page.items.map((product) => (
            <CatalogRow
              key={product.product_id}
              product={product}
              inCart={cartSet.has(product.product_id)}
              busy={busy && pendingAdd === product.product_id}
              onAdd={onAdd}
            />
          ))}
        </VStack>
      )}

      {page && page.total > PAGE_SIZE && (
        <HStack justify="space-between" gap="2">
          <Button
            size="xs"
            variant="outline"
            disabled={offset === 0 || loading}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Anterior
          </Button>
          <Text textStyle="xs" color="fg.muted">
            Página {Math.floor(offset / PAGE_SIZE) + 1} de{" "}
            {Math.max(1, Math.ceil(page.total / PAGE_SIZE))}
          </Text>
          <Button
            size="xs"
            variant="outline"
            disabled={offset + PAGE_SIZE >= page.total || loading}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Siguiente
          </Button>
        </HStack>
      )}
    </VStack>
  )
}
