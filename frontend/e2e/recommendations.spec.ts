import { expect, test } from "@playwright/test"

// T01–T04, T08 y T09 contra el backend real (uvicorn + modelo en artifacts/).
// El carrito inicial [24852, 13176] dispara la consulta automáticamente
// (debounce de 400 ms al montar y al cambiar el carrito).

test("T01: recomendaciones reales con model_version, score y source", async ({
  page,
}) => {
  await page.goto("/")
  await expect(page.getByText("Backend FastAPI conectado")).toBeVisible()
  await expect(page.getByText(/^ID \d+/).first()).toBeVisible()
  await expect(page.getByText(/^modelo \d/)).toBeVisible()
  await expect(page.getByText(/score \d+\.\d+/).first()).toBeVisible()
})

test("T02: aceptar envía accepted, agrega al carrito y retira la tarjeta", async ({
  page,
}) => {
  await page.goto("/")
  const accept = page
    .getByRole("button", { name: /^Agregar / })
    .and(page.locator("button:not([disabled])"))
    .first()
  await expect(accept).toBeEnabled({ timeout: 15_000 })
  const acceptedLabel = await accept.getAttribute("aria-label")
  expect(acceptedLabel, "aria-label de la tarjeta aceptada").toBeTruthy()
  await accept.click()
  await expect(
    page.getByText(/aceptado — evento «accepted» confirmado por el backend/),
  ).toBeVisible()
  // La tarjeta aceptada desaparece del widget…
  await expect(
    page.getByRole("button", { name: acceptedLabel!, exact: true }),
  ).toHaveCount(0)
  // …y el producto entra al carrito real (2 iniciales + 1 aceptado).
  await expect(
    page.getByRole("button", { name: /^Quitar producto \d+ del carrito/ }),
  ).toHaveCount(3)
})

test("T03: rechazar envía rejected y retira la tarjeta", async ({ page }) => {
  await page.goto("/")
  const enabledReject = page
    .getByRole("button", { name: /^No me interesa / })
    .and(page.locator("button:not([disabled])"))
  await expect(enabledReject.nth(1)).toBeEnabled({ timeout: 15_000 })
  const rejectedLabel = await enabledReject.nth(1).getAttribute("aria-label")
  expect(rejectedLabel, "aria-label de la tarjeta rechazada").toBeTruthy()
  await enabledReject.nth(1).click()
  // La tarjeta rechazada desaparece y el widget consulta reemplazos.
  await expect(
    page.getByRole("button", { name: rejectedLabel!, exact: true }),
  ).toHaveCount(0)
  await expect(page.getByText(/score \d+\.\d+/).first()).toBeVisible({
    timeout: 15_000,
  })
})

test("T04: los IDs rechazados no se repiten al re-solicitar", async ({
  page,
}) => {
  await page.goto("/")
  const enabledReject = page
    .getByRole("button", { name: /^No me interesa / })
    .and(page.locator("button:not([disabled])"))
  await expect(enabledReject.nth(1)).toBeEnabled({ timeout: 15_000 })
  // ID de la segunda tarjeta de recomendación (las del carrito no llevan categoría).
  const idText = await page.getByText(/^ID \d+ · .+ · /).nth(1).textContent()
  const rejectedId = idText?.match(/ID (\d+)/)?.[1]
  expect(rejectedId, "ID de la tarjeta rechazada").toBeTruthy()
  await enabledReject.nth(1).click()
  await page.getByRole("button", { name: "Pedir recomendaciones" }).click()
  await expect(page.getByText(/score \d+\.\d+/).first()).toBeVisible()
  // El backend filtra los rechazados: el producto no vuelve en la nueva respuesta.
  await expect(
    page.getByText(new RegExp(`^ID ${rejectedId} ·`)),
  ).toHaveCount(0)
})

test("T08: solicitud inválida muestra HTTP 422 legible", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByText(/^ID \d+/).first()).toBeVisible()
  await page.getByRole("button", { name: /Probar solicitud inválida/ }).click()
  await expect(page.getByText("Error del backend")).toBeVisible()
  await expect(page.getByText(/422/).first()).toBeVisible()
})

test("T09: carrito vacío envía [] real y muestra fallback + warnings", async ({
  page,
}) => {
  await page.goto("/")
  await expect(page.getByText(/^ID \d+/).first()).toBeVisible()
  await page
    .getByRole("button", { name: "Quitar producto 24852 del carrito" })
    .click()
  await page
    .getByRole("button", { name: "Quitar producto 13176 del carrito" })
    .click()
  await expect(page.getByText(/El carrito está vacío \(T09\)/)).toBeVisible()
  // El debounce re-consulta con cart: [] real; el backend responde fallback.
  await expect(page.getByText("fallback: true")).toBeVisible()
  await expect(page.getByText(/Advertencias del backend:/)).toBeVisible()
})
