import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { after, before, test } from "node:test"
import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { createServer } from "vite"

let server
let html

before(async () => {
  server = await createServer({
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    appType: "custom",
    optimizeDeps: { noDiscovery: true, include: [], entries: [] },
  })
  const { default: App } = await server.ssrLoadModule("/src/App.tsx")
  html = renderToStaticMarkup(createElement(App))
})

after(async () => {
  await server?.close()
})

test("navigation and conversion links resolve to page sections, contact or the console", () => {
  const anchors = [...html.matchAll(/href="#([^"]+)"/g)].map((match) => match[1])
  assert.ok(anchors.includes("calculadora"))
  for (const anchor of anchors) {
    assert.ok(html.includes(`id="${anchor}"`), `Missing destination: ${anchor}`)
  }
  assert.match(html, /href="mailto:contato@integrix\.com\.br/)
  const destination = server.config.env.VITE_OPS_CONSOLE_URL || "/dashboard"
  const expectedHref = renderToStaticMarkup(createElement("a", { href: destination })).match(/href="[^"]*"/)[0]
  assert.ok(html.includes(expectedHref), "The client link must use the configured console destination")
})

test("illustrative operations are visibly labeled instead of presented as live results", () => {
  assert.match(html, /Dados ilustrativos/)
  assert.doesNotMatch(html, /Operação ao vivo|Escala ilimitada|Histórico enviado em 2 segundos/)
})

test("calculator initially renders the actual cost comparison and its limitations", () => {
  // 6 × 2,500 × 1.70 = 25,500; 60% = 15,300; 8,000 × .16 × 5.07 = 6,489.60.
  for (const amount of ["25.500", "15.300", "6.490", "8.810", "105.725"]) {
    assert.ok(html.includes(amount), `Missing initial estimate: ${amount}`)
  }
  assert.match(html, /US\$ 0,16/)
  assert.match(html, /economia garantida/)
  assert.match(html, /implantação/)
})

test("all six calculator assumptions support both sliders and precise numeric entry", () => {
  assert.equal([...html.matchAll(/type="range"/g)].length, 6)
  assert.equal([...html.matchAll(/type="number"/g)].length, 6)
  assert.match(html, /Restaurar valores/)
})

test("calculator distinguishes potential savings, a break-even and a higher AI cost", async () => {
  const { calculateEstimate } = await server.ssrLoadModule("/src/estimate.ts")
  const assumptions = { people: 6, salary: 2500, overhead: 70, routineShare: 60, monthlyMinutes: 8000, exchangeRate: 5.07 }
  const baseline = calculateEstimate(assumptions)
  assert.equal(baseline.monthlyTeamCost, 25500)
  assert.equal(baseline.routineCost, 15300)
  assert.ok(Math.abs(baseline.monthlyAiCost - 6489.6) < 0.001)
  assert.ok(Math.abs(baseline.monthlySavings - 8810.4) < 0.001)
  assert.ok(Math.abs(baseline.annualSavings - 105724.8) < 0.001)

  const expensive = calculateEstimate({ ...assumptions, monthlyMinutes: 50000, exchangeRate: 7 })
  assert.equal(expensive.monthlyAiCost, 56000)
  assert.equal(expensive.monthlyDifference, -40700)
  assert.equal(expensive.monthlySavings, 0)
  assert.equal(expensive.annualSavings, 0)

  const breakEven = calculateEstimate({ people: 1, salary: 2000, overhead: 60, routineShare: 20, monthlyMinutes: 1000, exchangeRate: 4 })
  assert.equal(breakEven.monthlyDifference, 0)
  assert.equal(breakEven.savingsPercentage, 0)
})

test("mathematically equal costs are break-even despite floating-point residue", async () => {
  const { calculateEstimate } = await server.ssrLoadModule("/src/estimate.ts")
  // Both sides are R$1,320: 1,500 × 2.2 × 40%, and 1,500 × .16 × 5.5.
  const result = calculateEstimate({ people: 1, salary: 1500, overhead: 120, routineShare: 40, monthlyMinutes: 1500, exchangeRate: 5.5 })
  assert.equal(result.monthlyDifference, 0)
  assert.equal(result.savingsPercentage, 0)
})

test("Vercel configuration keeps the landing as a static SPA", async () => {
  const config = JSON.parse(await readFile(new URL("../vercel.json", import.meta.url), "utf8"))
  assert.deepEqual(config.rewrites, [{ source: "/(.*)", destination: "/index.html" }])
  assert.equal(config.outputDirectory, "dist")
})
