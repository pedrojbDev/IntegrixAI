const WINDOW_LABELS = {
  "15m": "15 minutos",
  "1h": "1 hora",
  "24h": "24 horas",
  "7d": "7 dias",
}

const STORAGE_KEY = "integrix.dashboard.filters"

const bootstrap = readBootstrap()
const numberFmt = new Intl.NumberFormat("pt-BR")
const moneyFmt = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 6,
})

const state = {
  loading: false,
  syncing: false,
  filters: loadStoredFilters(),
}

const refs = {
  window: document.getElementById("window"),
  tenant: document.getElementById("tenant"),
  assistant: document.getElementById("assistant"),
  refreshBtn: document.getElementById("refresh-btn"),
  syncBtn: document.getElementById("sync-btn"),
  activeContext: document.getElementById("active-context"),
  healthBadge: document.getElementById("health-badge"),
  healthSummary: document.getElementById("health-summary"),
  lastRefresh: document.getElementById("last-refresh"),
  statusLine: document.getElementById("status-line"),
  total: document.getElementById("k-total"),
  windowLabel: document.getElementById("k-window"),
  successRate: document.getElementById("k-success-rate"),
  successCount: document.getElementById("k-success-count"),
  handoffRate: document.getElementById("k-handoff-rate"),
  handoffCount: document.getElementById("k-handoff-count"),
  cost: document.getElementById("k-cost"),
  costCalls: document.getElementById("k-cost-calls"),
  failureRate: document.getElementById("k-failure-rate"),
  failureCount: document.getElementById("k-failure-count"),
  coverage: document.getElementById("k-coverage"),
  coverageMeta: document.getElementById("k-coverage-meta"),
  costAvg: document.getElementById("k-cost-avg"),
  duration: document.getElementById("k-duration"),
  callsTimeline: document.getElementById("calls-timeline"),
  costTimeline: document.getElementById("cost-timeline"),
  signalSummary: document.getElementById("signal-summary"),
  alertsList: document.getElementById("alerts-list"),
  focusList: document.getElementById("focus-list"),
  toolsTable: document.getElementById("tools-table"),
  tableEmpty: document.getElementById("table-empty"),
}

hydrateControls()
bindEvents()
applyContextText()
refreshAll()
window.setInterval(refreshAll, bootstrap.refreshIntervalMs || 45_000)

function readBootstrap() {
  const element = document.getElementById("dashboard-bootstrap")
  if (!element) {
    return { token: "", headerName: "x-ops-token", refreshIntervalMs: 45_000 }
  }

  try {
    return JSON.parse(element.textContent || "{}")
  } catch (_error) {
    return { token: "", headerName: "x-ops-token", refreshIntervalMs: 45_000 }
  }
}

function loadStoredFilters() {
  const fallback = { window: "24h", tenant: "", assistant: "" }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return fallback
    }

    const parsed = JSON.parse(raw)
    return {
      window: WINDOW_LABELS[parsed.window] ? parsed.window : fallback.window,
      tenant: typeof parsed.tenant === "string" ? parsed.tenant : "",
      assistant: typeof parsed.assistant === "string" ? parsed.assistant : "",
    }
  } catch (_error) {
    return fallback
  }
}

function persistFilters() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state.filters))
  } catch (_error) {
    // Best effort only.
  }
}

function hydrateControls() {
  refs.window.value = state.filters.window
  refs.tenant.value = state.filters.tenant
  refs.assistant.value = state.filters.assistant
}

function bindEvents() {
  refs.refreshBtn.addEventListener("click", () => refreshAll(true))
  refs.syncBtn.addEventListener("click", syncCosts)

  refs.window.addEventListener("change", () => {
    syncFiltersFromControls()
    refreshAll(true)
  })

  for (const field of [refs.tenant, refs.assistant]) {
    field.addEventListener("change", () => {
      syncFiltersFromControls()
      refreshAll(true)
    })
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        syncFiltersFromControls()
        refreshAll(true)
      }
    })
  }
}

function syncFiltersFromControls() {
  state.filters = {
    window: refs.window.value,
    tenant: refs.tenant.value.trim(),
    assistant: refs.assistant.value.trim(),
  }
  persistFilters()
  applyContextText()
}

function applyContextText() {
  const parts = [`Janela ${WINDOW_LABELS[state.filters.window]}`]
  if (state.filters.tenant) {
    parts.push(`tenant ${state.filters.tenant}`)
  } else {
    parts.push("visão geral")
  }
  if (state.filters.assistant) {
    parts.push(`assistant ${state.filters.assistant}`)
  }
  refs.activeContext.textContent = parts.join(" | ")
}

function setActionState() {
  refs.refreshBtn.disabled = state.loading || state.syncing
  refs.syncBtn.disabled = state.syncing
  refs.refreshBtn.textContent = state.loading ? "Atualizando..." : "Atualizar"
  refs.syncBtn.textContent = state.syncing ? "Sincronizando..." : "Sincronizar custos"
}

async function refreshAll(manual = false) {
  syncFiltersFromControls()
  state.loading = true
  setActionState()
  refs.statusLine.textContent = manual
    ? "Atualização manual em andamento."
    : "Atualização automática em andamento."

  try {
    const [overview, costs, tools] = await Promise.all([
      apiGet("/ops/dashboard/overview"),
      apiGet("/ops/dashboard/costs"),
      apiGet("/ops/dashboard/tools"),
    ])

    const model = deriveModel({ overview, costs, tools })
    renderDashboard(model)
    refs.lastRefresh.textContent = `Atualizado às ${new Date().toLocaleTimeString("pt-BR")}`
    refs.statusLine.textContent = "Leitura operacional atualizada com sucesso."
  } catch (error) {
    renderFailure(error)
    refs.lastRefresh.textContent = "Falha ao atualizar"
    refs.statusLine.textContent = `Falha ao carregar dados: ${error.message}`
  } finally {
    state.loading = false
    setActionState()
  }
}

async function syncCosts() {
  state.syncing = true
  setActionState()
  refs.statusLine.textContent = "Sincronização de custos em andamento."

  try {
    const response = await fetch("/ops/costs/sync", {
      method: "POST",
      headers: buildHeaders(),
    })

    if (!response.ok) {
      throw new Error(`${response.status} ao sincronizar custos`)
    }

    const payload = await response.json()
    refs.statusLine.textContent = `Sync concluído: ${payload.result.processed} processadas, ${payload.result.created} novas.`
    await refreshAll(true)
  } catch (error) {
    refs.statusLine.textContent = `Sync falhou: ${error.message}`
  } finally {
    state.syncing = false
    setActionState()
  }
}

async function apiGet(path) {
  const url = new URL(path, window.location.origin)
  url.searchParams.set("window", state.filters.window)
  if (state.filters.tenant) {
    url.searchParams.set("tenant_id", state.filters.tenant)
  }
  if (state.filters.assistant) {
    url.searchParams.set("assistant_id", state.filters.assistant)
  }

  const response = await fetch(url, { headers: buildHeaders() })
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`)
  }
  return response.json()
}

function buildHeaders() {
  return {
    [bootstrap.headerName || "x-ops-token"]: bootstrap.token || "",
  }
}

function deriveModel({ overview, costs, tools }) {
  const totalCalls = Number(overview.kpis.total_calls || 0)
  const successCalls = Number(overview.kpis.success_calls || 0)
  const failedCalls = Number(overview.kpis.failed_calls || 0)
  const handoffCalls = Number(overview.kpis.handoff_calls || 0)
  const avgDurationMs = Number(overview.kpis.avg_duration_ms || 0)
  const callsWithCost = Number(costs.summary.calls_with_cost || 0)
  const totalCostUsd = Number(costs.summary.total_cost_usd || 0)
  const avgCostUsd = Number(costs.summary.avg_cost_per_call_usd || 0)
  const successRate = rateOf(successCalls, totalCalls)
  const failureRate = rateOf(failedCalls, totalCalls)
  const handoffRate = rateOf(handoffCalls, totalCalls)
  const coverageRate = rateOf(callsWithCost, totalCalls)

  const topVolume = sortByMetric(tools.items, "total_calls")
  const topFailure = [...tools.items]
    .filter((item) => Number(item.total_calls || 0) > 0)
    .sort((left, right) => Number(right.failure_rate_pct || 0) - Number(left.failure_rate_pct || 0))
  const topCost = sortByMetric(tools.items, "total_cost_usd")

  const health = deriveHealth({ totalCalls, failureRate, handoffRate, coverageRate })

  return {
    overview,
    tools: tools.items,
    callsTimeline: overview.series || [],
    costTimeline: costs.series || [],
    health,
    kpis: {
      totalCalls,
      successCalls,
      failedCalls,
      handoffCalls,
      avgDurationMs,
      callsWithCost,
      totalCostUsd,
      avgCostUsd,
      successRate,
      failureRate,
      handoffRate,
      coverageRate,
    },
    signals: buildSignals({
      health,
      totalCalls,
      callsWithCost,
      avgDurationMs,
      successRate,
      failureRate,
    }),
    alerts: buildAlerts({
      totalCalls,
      failureRate,
      handoffRate,
      coverageRate,
      callsWithCost,
      health,
    }),
    focusItems: buildFocusItems({
      topVolume: topVolume[0],
      topFailure: topFailure[0],
      topCost: topCost[0],
    }),
  }
}

function deriveHealth({ totalCalls, failureRate, handoffRate, coverageRate }) {
  if (totalCalls === 0) {
    return {
      label: "Sem dados",
      className: "health-neutral",
      summary: "Nenhuma call encontrada para a janela e filtros selecionados.",
    }
  }

  if (failureRate >= 25 || handoffRate >= 40 || coverageRate < 50) {
    return {
      label: "Crítico",
      className: "health-critical",
      summary: "A operação está pressionada por falha, handoff alto ou baixa cobertura de custo.",
    }
  }

  if (failureRate >= 10 || handoffRate >= 20 || coverageRate < 80) {
    return {
      label: "Atenção",
      className: "health-warning",
      summary: "Há sinais de atenção, mas a operação ainda segue controlada.",
    }
  }

  return {
    label: "Estável",
    className: "health-stable",
    summary: "A janela está saudável nas métricas principais.",
  }
}

function buildSignals({ health, totalCalls, callsWithCost, avgDurationMs, successRate, failureRate }) {
  return [
    {
      label: "Leitura geral",
      value: health.label,
      caption: health.summary,
    },
    {
      label: "Cobertura",
      value: totalCalls > 0 ? `${numberFmt.format(callsWithCost)} / ${numberFmt.format(totalCalls)}` : "0 / 0",
      caption: "Calls com custo sincronizado dentro da janela atual.",
    },
    {
      label: "Eficiência",
      value: formatPercent(successRate),
      caption: `Falha em ${formatPercent(failureRate)} e duração média de ${formatDuration(avgDurationMs)}.`,
    },
  ]
}

function buildAlerts({ totalCalls, failureRate, handoffRate, coverageRate, callsWithCost, health }) {
  if (totalCalls === 0) {
    return [
      {
        level: "warning",
        title: "Sem volume na janela",
        body: "Ajuste a janela ou revise a ingestão de eventos para gerar leitura operacional.",
      },
    ]
  }

  const alerts = []

  if (health.label === "Estável") {
    alerts.push({
      level: "stable",
      title: "Operação sob controle",
      body: "Falha, handoff e cobertura estão dentro da faixa esperada.",
    })
  }

  if (failureRate >= 10) {
    alerts.push({
      level: failureRate >= 25 ? "critical" : "warning",
      title: "Falha acima do esperado",
      body: `A taxa de falha chegou a ${formatPercent(failureRate)} na janela atual.`,
    })
  }

  if (handoffRate >= 20) {
    alerts.push({
      level: handoffRate >= 40 ? "critical" : "warning",
      title: "Handoff elevado",
      body: `${formatPercent(handoffRate)} das chamadas terminaram em transferência para humano.`,
    })
  }

  if (coverageRate < 80) {
    alerts.push({
      level: coverageRate < 50 ? "critical" : "warning",
      title: "Cobertura de custo incompleta",
      body: `${numberFmt.format(callsWithCost)} chamadas com custo sincronizado na janela atual.`,
    })
  }

  return alerts.slice(0, 3)
}

function buildFocusItems({ topVolume, topFailure, topCost }) {
  return [
    topVolume
      ? {
          label: "Maior volume",
          title: topVolume.tool_name,
          meta: `${numberFmt.format(topVolume.total_calls || 0)} calls`,
          caption: "Tool com maior pressão operacional na janela.",
        }
      : null,
    topFailure
      ? {
          label: "Maior falha",
          title: topFailure.tool_name,
          meta: formatPercent(topFailure.failure_rate_pct || 0),
          caption: "Prioridade mais clara de revisão operacional.",
        }
      : null,
    topCost
      ? {
          label: "Maior custo",
          title: topCost.tool_name,
          meta: formatUsd(topCost.total_cost_usd || 0),
          caption: "Tool com maior impacto financeiro agregado.",
        }
      : null,
  ].filter(Boolean)
}

function renderDashboard(model) {
  renderHealth(model.health)
  renderKpis(model)
  renderSignals(model.signals)
  renderAlerts(model.alerts)
  renderFocusItems(model.focusItems)
  renderCallsTimeline(model.callsTimeline)
  renderCostTimeline(model.costTimeline)
  renderToolsTable(model.tools)
}

function renderFailure(error) {
  renderHealth({
    label: "Crítico",
    className: "health-critical",
    summary: `Não foi possível carregar o painel: ${error.message}`,
  })
  renderSignals([
    {
      label: "Estado do painel",
      value: "Erro",
      caption: "A interface carregou, mas a camada de dados não respondeu corretamente.",
    },
    {
      label: "Próximo passo",
      value: "Revisar acesso",
      caption: "Confirme token operacional, banco habilitado e disponibilidade das rotas /ops.",
    },
    {
      label: "Ação sugerida",
      value: "Atualizar",
      caption: "Faça nova tentativa após validar a conectividade da aplicação.",
    },
  ])
  renderAlerts([
    {
      level: "critical",
      title: "Leitura interrompida",
      body: `Não foi possível consultar as métricas: ${error.message}.`,
    },
  ])
  renderFocusItems([])
  renderCallsTimeline([])
  renderCostTimeline([])
  renderToolsTable([])
}

function renderHealth(health) {
  refs.healthBadge.className = `health-badge ${health.className}`
  refs.healthBadge.textContent = health.label
  refs.healthSummary.textContent = health.summary
}

function renderKpis(model) {
  const { kpis, overview } = model
  refs.total.textContent = numberFmt.format(kpis.totalCalls)
  refs.windowLabel.textContent = `Janela ${WINDOW_LABELS[overview.window]}`
  refs.successRate.textContent = formatPercent(kpis.successRate)
  refs.successCount.textContent = `${numberFmt.format(kpis.successCalls)} calls resolvidas`
  refs.handoffRate.textContent = formatPercent(kpis.handoffRate)
  refs.handoffCount.textContent = `${numberFmt.format(kpis.handoffCalls)} transferências`
  refs.cost.textContent = formatUsd(kpis.totalCostUsd)
  refs.costCalls.textContent = `${numberFmt.format(kpis.callsWithCost)} calls com custo`
  refs.failureRate.textContent = formatPercent(kpis.failureRate)
  refs.failureCount.textContent = `${numberFmt.format(kpis.failedCalls)} chamadas falhas`
  refs.coverage.textContent = formatPercent(kpis.coverageRate)
  refs.coverageMeta.textContent =
    kpis.totalCalls > 0
      ? `${numberFmt.format(kpis.callsWithCost)} de ${numberFmt.format(kpis.totalCalls)} com custo`
      : "Sem correlação ainda"
  refs.costAvg.textContent = formatUsd(kpis.avgCostUsd)
  refs.duration.textContent = formatDuration(kpis.avgDurationMs)
}

function renderSignals(signals) {
  refs.signalSummary.replaceChildren()

  for (const signal of signals) {
    const card = document.createElement("article")
    card.className = "summary-card"

    const label = document.createElement("span")
    label.className = "label"
    label.textContent = signal.label

    const value = document.createElement("strong")
    value.textContent = signal.value

    const caption = document.createElement("p")
    caption.className = "summary-caption"
    caption.textContent = signal.caption

    card.append(label, value, caption)
    refs.signalSummary.appendChild(card)
  }
}

function renderAlerts(alerts) {
  refs.alertsList.replaceChildren()

  for (const alert of alerts) {
    const card = document.createElement("article")
    card.className = `alert-card alert-${alert.level}`

    const title = document.createElement("strong")
    title.textContent = alert.title

    const body = document.createElement("p")
    body.textContent = alert.body

    card.append(title, body)
    refs.alertsList.appendChild(card)
  }
}

function renderFocusItems(items) {
  refs.focusList.replaceChildren()

  if (!items.length) {
    refs.focusList.appendChild(buildEmptyBlock("Sem dados suficientes para destacar tools na janela atual."))
    return
  }

  for (const item of items) {
    const card = document.createElement("article")
    card.className = "focus-card"

    const label = document.createElement("span")
    label.className = "label"
    label.textContent = item.label

    const title = document.createElement("strong")
    title.textContent = item.title

    const meta = document.createElement("span")
    meta.className = "focus-meta"
    meta.textContent = item.meta

    const caption = document.createElement("p")
    caption.textContent = item.caption

    card.append(label, title, meta, caption)
    refs.focusList.appendChild(card)
  }
}

function renderCallsTimeline(items) {
  refs.callsTimeline.replaceChildren()

  if (!items.length) {
    refs.callsTimeline.appendChild(buildEmptyBlock("Sem buckets de chamadas para a janela atual."))
    return
  }

  const visible = items.slice(-10)
  const maxCalls = Math.max(1, ...visible.map((item) => Number(item.calls || 0)))

  for (const item of visible) {
    const calls = Number(item.calls || 0)
    const handoffs = Number(item.handoffs || 0)
    const row = document.createElement("article")
    row.className = "timeline-row"

    const head = document.createElement("div")
    head.className = "timeline-head"
    head.append(
      buildText("strong", "timeline-title", formatBucket(item.timestamp, state.filters.window)),
      buildText("span", "timeline-value", `${numberFmt.format(calls)} calls`),
    )

    const bar = document.createElement("div")
    bar.className = "timeline-bar"
    bar.style.setProperty("--primary-width", `${Math.max((calls / maxCalls) * 100, calls > 0 ? 8 : 0)}%`)
    bar.style.setProperty("--secondary-width", `${calls > 0 ? (handoffs / maxCalls) * 100 : 0}%`)
    bar.append(
      buildText("div", "timeline-primary", ""),
      buildText("div", "timeline-secondary", ""),
      buildText("div", "", ""),
    )

    const foot = document.createElement("div")
    foot.className = "timeline-foot"
    foot.append(
      buildText("span", "", `Handoff ${numberFmt.format(handoffs)}`),
      buildText("span", "", `Taxa ${formatPercent(rateOf(handoffs, calls))}`),
    )

    row.append(head, bar, foot)
    refs.callsTimeline.appendChild(row)
  }
}

function renderCostTimeline(items) {
  refs.costTimeline.replaceChildren()

  if (!items.length) {
    refs.costTimeline.appendChild(buildEmptyBlock("Nenhum bucket de custo disponível para os filtros atuais."))
    return
  }

  const visible = items.slice(-10)
  const maxCost = Math.max(1, ...visible.map((item) => Number(item.cost_usd || 0)))

  for (const item of visible) {
    const cost = Number(item.cost_usd || 0)
    const calls = Number(item.calls || 0)
    const row = document.createElement("article")
    row.className = "timeline-row"

    const head = document.createElement("div")
    head.className = "timeline-head"
    head.append(
      buildText("strong", "timeline-title", formatBucket(item.timestamp, state.filters.window)),
      buildText("span", "timeline-value", formatUsd(cost)),
    )

    const bar = document.createElement("div")
    bar.className = "timeline-bar"
    bar.style.setProperty("--primary-width", `${Math.max((cost / maxCost) * 100, cost > 0 ? 8 : 0)}%`)
    bar.style.setProperty("--secondary-width", "0%")
    bar.append(
      buildText("div", "timeline-cost", ""),
      buildText("div", "", ""),
      buildText("div", "", ""),
    )

    const foot = document.createElement("div")
    foot.className = "timeline-foot"
    foot.append(
      buildText("span", "", `${numberFmt.format(calls)} calls`),
      buildText("span", "", calls > 0 && cost > 0 ? `${formatUsd(cost / calls)} por call` : "Sem custo unitário"),
    )

    row.append(head, bar, foot)
    refs.costTimeline.appendChild(row)
  }
}

function renderToolsTable(items) {
  refs.toolsTable.replaceChildren()
  refs.tableEmpty.classList.toggle("hidden", items.length > 0)

  for (const item of items) {
    const row = document.createElement("tr")
    appendCell(row, item.tool_name, "tool-name")
    appendCell(row, numberFmt.format(item.total_calls || 0))
    appendCell(row, formatPercent(rateOf(item.success_calls, item.total_calls)))
    appendCell(row, formatPercent(item.failure_rate_pct || 0))
    appendCell(row, numberFmt.format(item.handoff_calls || 0))
    appendCell(row, formatUsd(item.total_cost_usd || 0))
    appendCell(row, formatUsd(item.avg_cost_per_call_usd || 0))
    refs.toolsTable.appendChild(row)
  }
}

function appendCell(row, value, className = "") {
  const cell = document.createElement("td")
  if (className) {
    cell.className = className
  }
  cell.textContent = value
  row.appendChild(cell)
}

function buildEmptyBlock(text) {
  const element = document.createElement("div")
  element.className = "empty-state"
  element.textContent = text
  return element
}

function buildText(tagName, className, text) {
  const element = document.createElement(tagName)
  if (className) {
    element.className = className
  }
  element.textContent = text
  return element
}

function sortByMetric(items, key) {
  return [...items].sort((left, right) => Number(right[key] || 0) - Number(left[key] || 0))
}

function rateOf(numerator, denominator) {
  const base = Number(denominator || 0)
  if (base <= 0) {
    return 0
  }
  return (Number(numerator || 0) / base) * 100
}

function formatPercent(value) {
  return `${Number(value || 0).toFixed(1).replace(".", ",")}%`
}

function formatUsd(value) {
  return moneyFmt.format(Number(value || 0))
}

function formatDuration(value) {
  const ms = Number(value || 0)
  if (ms >= 60_000) {
    return `${(ms / 60_000).toFixed(1).replace(".", ",")} min`
  }
  if (ms >= 1_000) {
    return `${(ms / 1_000).toFixed(1).replace(".", ",")} s`
  }
  return `${Math.round(ms)} ms`
}

function formatBucket(timestamp, windowKey) {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return "Bucket inválido"
  }

  if (windowKey === "7d") {
    return date.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
    })
  }

  return date.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  })
}
