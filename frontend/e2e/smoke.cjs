/* Smoke E2E de NEXTCART frontend contra el backend real (sin mocks).
 *
 * Requiere Playwright global: pnpm add -g playwright && playwright install chromium
 * El módulo global de pnpm no está en un node_modules plano, así que este script
 * se invoca con NODE_PATH apuntando al node_modules del paquete global:
 *   $env:NODE_PATH = "<pnpm root -g>\<hash>\node_modules"; node e2e/smoke.cjs [offline]
 *
 * Fases:
 *   node e2e/smoke.cjs offline   -> con el backend APAGADO: badge "Backend no disponible"
 *   node e2e/smoke.cjs           -> flujo completo: health, recomendaciones, feedback, 422
 */
const { chromium } = require("playwright")

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173"
const OFFLINE = process.argv.includes("offline")

const results = []
function check(name, condition) {
  if (!condition) throw new Error(`FALLO: ${name}`)
  results.push(name)
  console.log(`  ok  ${name}`)
}

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage()
  page.setDefaultTimeout(20000)
  const pageErrors = []
  page.on("pageerror", (err) => pageErrors.push(String(err)))

  try {
    await page.goto(BASE_URL, { timeout: 60000 })
    await page.getByText("Checkout de demostración").waitFor()

    if (OFFLINE) {
      console.log("Fase offline (backend apagado):")
      await page
        .getByText("Backend no disponible")
        .first()
        .waitFor()
      check('badge "Backend no disponible" visible', true)
      check(
        "sin recomendaciones antes de pedirlas",
        await page.getByText("Sin recomendaciones todavía").isVisible(),
      )
      await page
        .getByRole("button", { name: "Pedir recomendaciones" })
        .click()
      await page.getByText("Error del backend").waitFor()
      check(
        "error de conexión mostrado sin datos simulados",
        await page
          .getByText(/No se pudo conectar|conexión/i)
          .first()
          .isVisible(),
      )
    } else {
      console.log("Fase completa (backend encendido):")
      await page.getByText("Backend FastAPI conectado").waitFor()
      check('badge "Backend FastAPI conectado" visible', true)
      check(
        "sin recomendaciones antes de pedirlas",
        await page.getByText("Sin recomendaciones todavía").isVisible(),
      )

      await page.getByRole("button", { name: "Pedir recomendaciones" }).click()
      await page.getByText(/^ID \d+/).first().waitFor()
      const cards = await page.getByText(/^ID \d+/).count()
      check(`tarjetas de recomendación renderizadas (${cards})`, cards >= 1)
      await page.getByText(/^modelo \d/).waitFor()
      check("badge con model_version del backend visible", true)
      check(
        "score y source del backend visibles",
        await page.getByText(/score \d+\.\d+/).first().isVisible(),
      )

      await page.getByRole("button", { name: "Agregar", exact: true }).first().click()
      await page.getByText(/aceptado — evento «accepted» confirmado por el backend/).waitFor()
      check("alerta de aceptación con HTTP 202 confirmado", true)
      await page.getByText("aceptado", { exact: true }).first().waitFor()
      check('badge "aceptado" en la tarjeta', true)

      await page.getByRole("button", { name: "No me interesa" }).nth(1).click()
      await page.getByText("rechazado", { exact: true }).first().waitFor()
      check('badge "rechazado" en la segunda tarjeta', true)

      await page.getByRole("button", { name: /Probar solicitud inválida/ }).click()
      await page.getByText("Error del backend").waitFor()
      await page.getByText(/422/).first().waitFor()
      check("solicitud inválida muestra HTTP 422 legible", true)
    }

    check("sin excepciones JS en la página", pageErrors.length === 0)
    console.log(`\n${results.length} verificaciones OK`)
  } finally {
    if (pageErrors.length > 0) {
      console.log("\nExcepciones JS capturadas:")
      for (const err of pageErrors) console.log("  ", err.split("\n")[0])
    }
    await browser.close()
  }
}

main().catch((err) => {
  console.error(`\n${results.length} verificaciones OK antes del fallo`)
  console.error(err.message)
  process.exit(1)
})
