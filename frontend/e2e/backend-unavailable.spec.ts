import { expect, test } from "@playwright/test"

// Estados de backend no disponible. El caso de conexión caída se simula
// abortando la red desde el navegador (equivalente a un servidor apagado);
// T07 retransmite las respuestas REALES que produce src/backend.py arrancado
// sin NEXTCART_MODEL_PATH, para no depender de un segundo proceso de uvicorn.

test("backend apagado: badge y error de conexión sin datos simulados", async ({
  page,
}) => {
  await page.route("**/health", (route) => route.abort())
  await page.route("**/v1/**", (route) => route.abort())
  await page.goto("/")
  await expect(page.getByText("Backend no disponible").first()).toBeVisible()
  await page.getByRole("button", { name: "Pedir recomendaciones" }).click()
  await expect(page.getByText("Error del backend")).toBeVisible()
  await expect(
    page.getByText(/Sin conexión con el backend FastAPI/).first(),
  ).toBeVisible()
})

test("T07: modelo no cargado — badge degradado y 503 con instrucción", async ({
  page,
}) => {
  await page.route("**/health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "degraded",
        model_loaded: false,
        model_version: null,
        error: "NEXTCART_MODEL_PATH no está definido.",
      }),
    }),
  )
  await page.route("**/v1/recommendations", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        detail: {
          error: "model_not_loaded",
          detail: "NEXTCART_MODEL_PATH no está definido.",
          instruction:
            "Entrena el modelo localmente con src/train_agent.py y define " +
            "NEXTCART_MODEL_PATH apuntando al artefacto; reinicia o usa " +
            "/v1/admin/reload-model.",
        },
      }),
    }),
  )
  await page.goto("/")
  await expect(page.getByText("Backend degradado")).toBeVisible()
  await page.getByRole("button", { name: "Pedir recomendaciones" }).click()
  await expect(
    page.getByText(/HTTP 503 — el backend no tiene el modelo disponible/).first(),
  ).toBeVisible()
})
