import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

test("landing page uses corporate customer-friendly positioning and navigation targets", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8")

  assert.match(app, /IA de voz para operações de atendimento que exigem controle, integração e rastreabilidade\./)
  assert.match(app, /acompanhar a operação com segurança, auditoria e indicadores claros/)
  assert.match(app, /href=\{opsConsoleUrl\}/)
  assert.match(app, /mailto:contato@integrix\.com\.br/)
  assert.match(app, /Direcionamento inteligente de chamadas/)
  assert.match(app, /Painel de gestão operacional/)
  assert.match(app, /Passagem organizada para atendimento humano/)
})

test("hero includes a realistic business dashboard mockup", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8")

  assert.match(app, /Atendimentos hoje/)
  assert.match(app, /Taxa de resolução/)
  assert.match(app, /Tempo médio/)
  assert.match(app, /Custo estimado/)
  assert.match(app, /Últimos atendimentos/)
  assert.match(app, /Status das integrações/)
  assert.match(app, /Operação normal/)
  assert.match(app, /Auditoria ativa/)
  assert.match(app, /Integrações OK/)
})

test("landing styling is light corporate instead of dark technical", async () => {
  const css = await readFile(new URL("../src/index.css", import.meta.url), "utf8")
  const tailwind = await readFile(new URL("../tailwind.config.js", import.meta.url), "utf8")

  assert.match(css, /background:\s*#f8fbff/)
  assert.match(tailwind, /corporate/)
  assert.equal(css.includes("color-scheme: dark"), false)
  assert.equal(css.includes("#070b12"), false)
})

test("landing page avoids internal jargon and client-specific names", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8")
  const forbiddenTerms = [
    "tenant",
    "tool",
    "sync",
    "PB Saude",
    "PB Saúde",
    "Vapi",
    "DID",
    "webhook",
    "PostgreSQL",
    "HttpOnly",
    "idempot",
    "99.9%",
    "STEP",
    "terminal",
    "cyber",
  ]

  for (const term of forbiddenTerms) {
    assert.equal(app.includes(term), false, `Unexpected public jargon or internal term: ${term}`)
  }
})

test("Vercel configuration keeps the landing as a static SPA", async () => {
  const vercel = await readFile(new URL("../vercel.json", import.meta.url), "utf8")
  const config = JSON.parse(vercel)

  assert.deepEqual(config.rewrites, [{ source: "/(.*)", destination: "/index.html" }])
  assert.equal(config.outputDirectory, "dist")
})
