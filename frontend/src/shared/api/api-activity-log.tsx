import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react"
import type { ReactNode } from "react"
import { NextCartApiError, NextCartConnectionError } from "@/shared/api/nextcart-client"

export interface ApiLogEntry {
  id: number
  at: string
  method: string
  path: string
  status: number | null
  ok: boolean
  detail?: string
}

interface ApiActivityLog {
  entries: ApiLogEntry[]
  record(entry: Omit<ApiLogEntry, "id" | "at">): void
  clear(): void
}

const ApiActivityLogContext = createContext<ApiActivityLog | null>(null)

export function ApiActivityLogProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<ApiLogEntry[]>([])
  const nextId = useRef(1)

  const record = useCallback((entry: Omit<ApiLogEntry, "id" | "at">) => {
    setEntries((prev) =>
      [
        {
          ...entry,
          id: nextId.current++,
          at: new Date().toLocaleTimeString("es-CO", { hour12: false }),
        },
        ...prev,
      ].slice(0, 50),
    )
  }, [])

  const clear = useCallback(() => setEntries([]), [])

  const value = useMemo(() => ({ entries, record, clear }), [entries, record, clear])

  return <ApiActivityLogContext.Provider value={value}>{children}</ApiActivityLogContext.Provider>
}

export function useApiActivityLog(): ApiActivityLog {
  const ctx = useContext(ApiActivityLogContext)
  if (!ctx) throw new Error("useApiActivityLog must be used within ApiActivityLogProvider")
  return ctx
}

export function describeApiError(error: unknown): string {
  if (error instanceof NextCartApiError) {
    if (error.status === 503) {
      return `HTTP 503 — el backend no tiene el modelo disponible (degradado). ${error.message}`
    }
    if (error.status === 422) {
      return `HTTP 422 — solicitud inválida según el contrato del backend. ${error.message}`
    }
    if (error.status === 401 || error.status === 403) {
      return `HTTP ${error.status} — sesión no autorizada por el entorno o proxy. ${error.message}`
    }
    return `HTTP ${error.status} — ${error.message}`
  }
  if (error instanceof NextCartConnectionError) {
    return "Sin conexión con el backend FastAPI. Verifica que uvicorn esté corriendo en la URL configurada."
  }
  if (error instanceof Error) return error.message
  return String(error)
}
