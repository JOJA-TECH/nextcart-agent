import { useCallback, useEffect, useRef, useState } from "react"
import type { NextCartClient } from "@/shared/api/contracts"
import { describeApiError } from "@/shared/api/api-activity-log"

export type HealthState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: { status: string; model_loaded: boolean; model_version: string | null } }
  | { kind: "error"; error: string }

export type BackendStatus = "connected" | "degraded" | "unavailable"

export function useHealthPoll(client: NextCartClient, intervalMs = 15000) {
  const [health, setHealth] = useState<HealthState>({ kind: "idle" })
  const inFlight = useRef(false)

  const refresh = useCallback(async () => {
    if (inFlight.current) return
    inFlight.current = true
    setHealth({ kind: "loading" })
    try {
      const data = await client.health()
      setHealth({ kind: "ok", data })
    } catch (error) {
      setHealth({ kind: "error", error: describeApiError(error) })
    } finally {
      inFlight.current = false
    }
  }, [client])

  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh()
    }, intervalMs)
    return () => window.clearInterval(id)
  }, [refresh, intervalMs])

  const state: BackendStatus =
    health.kind === "ok"
      ? health.data.model_loaded && health.data.status === "ok"
        ? "connected"
        : "degraded"
      : health.kind === "error"
        ? "unavailable"
        : "unavailable"

  const detail =
    health.kind === "ok"
      ? health.data.model_loaded
        ? "modelo cargado"
        : "modelo no cargado"
      : health.kind === "error"
        ? undefined
        : "verificando…"

  return { health, state, detail, refresh }
}
