import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

test("landing leads with a business outcome and clear conversion paths", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8")

  assert.match(app, /Atenda mais\./)
  assert.match(app, /Sem inflar/)
  assert.match(app, /Quero ver na minha empresa/)
  assert.match(app, /Calcular meu potencial/)
  assert.match(app, /Agendar meu diagnóstico/)
  assert.match(app, /href=\{opsConsoleUrl\}/)
  assert.match(app, /mailto:contato@integrix\.com\.br/)
})

test("landing explains financial value without making an unsupported savings promise", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8")

  assert.match(app, /Encargos, benefícios e custos indiretos/)
  assert.match(app, /Parcela do trabalho que é repetitiva/)
  assert.match(app, /Minutos automatizáveis por mês/)
  assert.match(app, /US\$ 0,16 por minuto/)
  assert.match(app, /Economia líquida estimada/)
  assert.match(app, /Custo mensal estimado da IA/)
  assert.match(app, /Em 12 meses/)
  assert.match(app, /Não\s+representa receita adicional nem economia garantida/)
  assert.match(app, /Simulação educativa, não promessa de economia/)
  assert.match(app, /implantação e integrações podem alterar o resultado/)
  assert.doesNotMatch(app, /garantimos economia/i)
})

test("landing explains the full customer journey in plain language", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8")

  assert.match(app, /A gente entende a sua operação/)
  assert.match(app, /A IA aprende o caminho certo/)
  assert.match(app, /Você acompanha e melhora/)
  assert.match(app, /Sem fazer o cliente começar tudo de novo/)
  assert.match(app, /Uma IA que resolve tarefas, não apenas conversa/)
  assert.match(app, /Automação com controle\. Não uma caixa-preta\./)
})

test("landing presents a realistic management interface", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8")

  assert.match(app, /Atendimento inteligente/)
  assert.match(app, /atendimentos/)
  assert.match(app, /resolvidos pela IA/)
  assert.match(app, /tempo médio/)
  assert.match(app, /Visão da operação/)
  assert.match(app, /Operação saudável/)
})

test("landing uses a distinctive editorial brand system and accessible motion fallback", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8")
  const css = await readFile(new URL("../src/index.css", import.meta.url), "utf8")
  const tailwind = await readFile(new URL("../tailwind.config.js", import.meta.url), "utf8")

  assert.match(css, /Manrope/)
  assert.match(css, /IBM Plex Sans/)
  assert.match(css, /\.section-title\s*\{[^}]*color:\s*inherit/s)
  assert.match(app, /lg:grid-cols-\[1\.1fr_0\.9fr\] lg:items-center lg:gap-20/)
  assert.match(css, /prefers-reduced-motion/)
  assert.match(css, /focus-visible/)
  assert.match(tailwind, /#d9ff57/)
  assert.match(tailwind, /#14241c/)
  assert.equal(css.includes("color-scheme: dark"), false)
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

test("page metadata is written for decision makers, not technical readers", async () => {
  const html = await readFile(new URL("../index.html", import.meta.url), "utf8")

  assert.match(html, /Atenda mais sem inflar sua equipe/)
  assert.match(html, /reduzir trabalho repetitivo/)
  assert.match(html, /og:title/)
  assert.doesNotMatch(html, /infraestrutura enterprise/i)
})

test("Vercel configuration keeps the landing as a static SPA", async () => {
  const vercel = await readFile(new URL("../vercel.json", import.meta.url), "utf8")
  const config = JSON.parse(vercel)

  assert.deepEqual(config.rewrites, [{ source: "/(.*)", destination: "/index.html" }])
  assert.equal(config.outputDirectory, "dist")
})
