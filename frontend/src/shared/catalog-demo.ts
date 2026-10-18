export interface DemoCatalogEntry {
  id: number
  name: string
  price: number
  currency: string
  image: string
  category: string
}

/**
 * Catálogo local sintético de presentación (catalogo-demo).
 * Los nombres, precios, categorías e imágenes NO provienen del dataset
 * Instacart ni del backend: solo traducen los IDs numéricos reales del
 * modelo a tarjetas visuales para la demo.
 */
export const demoCatalog: Record<number, DemoCatalogEntry> = {
  24852: {
    id: 24852,
    name: "Bananas orgánicas",
    price: 8900,
    currency: "COP",
    image: "/catalog/product-24852.webp",
    category: "Frutas",
  },
  13176: {
    id: 13176,
    name: "Bolsa de limones",
    price: 12400,
    currency: "COP",
    image: "/catalog/product-13176.webp",
    category: "Frutas",
  },
  21137: {
    id: 21137,
    name: "Canasta de fresas",
    price: 15600,
    currency: "COP",
    image: "/catalog/product-21137.webp",
    category: "Frutas",
  },
  47209: {
    id: 47209,
    name: "Aguacate Hass",
    price: 9800,
    currency: "COP",
    image: "/catalog/product-47209.webp",
    category: "Frutas",
  },
  21903: {
    id: 21903,
    name: "Espinaca fresca",
    price: 7300,
    currency: "COP",
    image: "/catalog/product-21903.webp",
    category: "Verduras",
  },
  47626: {
    id: 47626,
    name: "Limón grande",
    price: 4100,
    currency: "COP",
    image: "/catalog/product-47626.webp",
    category: "Frutas",
  },
  27845: {
    id: 27845,
    name: "Leche entera",
    price: 6900,
    currency: "COP",
    image: "/catalog/product-27845.webp",
    category: "Lácteos",
  },
  16797: {
    id: 16797,
    name: "Moras azules",
    price: 18900,
    currency: "COP",
    image: "/catalog/product-16797.webp",
    category: "Frutas",
  },
  40338: {
    id: 40338,
    name: "Jugo de naranja",
    price: 11500,
    currency: "COP",
    image: "/catalog/product-40338.webp",
    category: "Bebidas",
  },
  4920: {
    id: 4920,
    name: "Granola con almendras",
    price: 22400,
    currency: "COP",
    image: "/catalog/product-4920.webp",
    category: "Desayuno",
  },
}

const FALLBACK_ENTRY: DemoCatalogEntry = {
  id: 0,
  name: "Producto de demostración",
  price: 9900,
  currency: "COP",
  image: "",
  category: "catálogo-demo",
}

export function lookupDemoProduct(productId: number): DemoCatalogEntry {
  const entry = demoCatalog[productId]
  if (entry) return entry
  return { ...FALLBACK_ENTRY, id: productId }
}

export const CATALOG_DEMO_TAG = "catálogo-demo"

export const DEMO_DATA_NOTE =
  "Los nombres, precios e imágenes son datos de presentación (catálogo-demo) y no provienen del backend. Las recomendaciones provienen exclusivamente del modelo local servido por FastAPI."
