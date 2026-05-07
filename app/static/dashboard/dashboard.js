const WINDOW_LABELS = {
  "15m": "15 minutos",
  "1h": "1 hora",
  "24h": "24 horas",
  "7d": "7 dias",
}

const WINDOW_TO_MINUTES = {
  "15m": 15,
  "1h": 60,
  "24h": 1440,
  "7d": 10080,
}

const FILTER_STORAGE_KEY = "integrix.console.filters"
const VIEW_STORAGE_KEY = "integrix.console.view"
const AUDIT_STORAGE_KEY = "integrix.console.audit"

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
  activeView: loadStoredView(),
  filters: loadStoredFilters(),
  audit: loadStoredAuditFilters(),
}

const refs = {
  globalMessage: document.getElementById("global-message"),
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
  viewTabs: [...document.querySelectorAll("[data-view]")],
  views: {
    overview: document.getElementById("view-overview"),
    diagnostics: document.getElementById("view-diagnostics"),
    audit: document.getElementById("view-audit"),
  },
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
  focusList: document.getElementById("focus-list"),
  toolsTable: document.getElementById("tools-table"),
  tableEmpty: document.getElementById("table-empty"),
  diagHealthState: document.getElementById("diag-health-state"),
  diagHealthCopy: document.getElementById("diag-health-copy"),
  diagSyncState: document.getElementById("diag-sync-state"),
  diagSyncAge: document.getElementById("diag-sync-age"),
  diagIdempotencyHits: document.getElementById("diag-idempotency-hits"),
  diagBusinessErrors: document.getElementById("diag-business-errors"),
  diagFailedSeries: document.getElementById("diag-failed-series"),
  diagIdempotencySeries: document.getElementById("diag-idempotency-series"),
  diagBusinessSeries: document.getElementById("diag-business-series"),
  diagTopFailures: document.getElementById("diag-top-failures"),
  diagTopHandoffs: document.getElementById("diag-top-handoffs"),
  diagBusinessTools: document.getElementById("diag-business-tools"),
  auditTotalCalls: document.getElementById("audit-total-calls"),
  auditSuccessCalls: document.getElementById("audit-success-calls"),
  auditFailedCalls: document.getElementById("audit-failed-calls"),
  auditHandoffCalls: document.getElementById("audit-handoff-calls"),
  auditLimit: document.getElementById("audit-limit"),
  auditTool: document.getElementById("audit-tool"),
  auditEvent: document.getElementById("audit-event"),
  auditOk: document.getElementById("audit-ok"),
  auditRefreshBtn: document.getElementById("audit-refresh-btn"),
  auditTableBody: document.getElementById("audit-table-body"),
  auditEmpty: document.getElementById("audit-empty"),
}

hydrateControls()
bindEvents()
applyContextText()
applyActiveView()
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

function loadStoredView() {
  const raw = window.localStorage.getItem(VIEW_STORAGE_KEY)
  return raw === "diagnostics" || raw === "audit" ? raw : "overview"
}

function loadStoredFilters() {
  const fallback = { window: "24h", tenant: "", assistant: "" }
  try {
    const raw = window.localStorage.getItem(FILTER_STORAGE_KEY)
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

function loadStoredAuditFilters() {
  const fallback = { limit: "50", toolName: "", eventType: "", ok: "all" }
  try {
    const raw = window.localStorage.getItem(AUDIT_STORAGE_KEY)
    if (!raw) {
      return fallback
    }
    const parsed = JSON.parse(raw)
    return {
      limit: ["25", "50", "100"].includes(parsed.limit) ? parsed.limit : fallback.limit,
      toolName: typeof parsed.toolName === "string" ? parsed.toolName : "",
      eventType: typeof parsed.eventType === "string" ? parsed.eventType : "",
      ok: ["all", "true", "false"].includes(parsed.ok) ? parsed.ok : "all",
    }
  } catch (_error) {
    return fallback
  }
}

function persistView() {
  window.localStorage.setItem(VIEW_STORAGE_KEY, state.activeView)
}

function persistFilters() {
  window.localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(state.filters))
}

function persistAuditFilters() {
  window.localStorage.setItem(AUDIT_STORAGE_KEY, JSON.stringify(state.audit))
}

function hydrateControls() {
  refs.window.value = state.filters.window
  refs.tenant.value = state.filters.tenant
  refs.assistant.value = state.filters.assistant
  refs.auditLimit.value = state.audit.limit
  refs.auditTool.value = state.audit.toolName
  refs.auditEvent.value = state.audit.eventType
  refs.auditOk.value = state.audit.ok
}

function bindEvents() {
  refs.refreshBtn.addEventListener("click", () => refreshAll(true))
  refs.syncBtn.addEventListener("click", syncCosts)
  refs.auditRefreshBtn.addEventListener("click", () => refreshAll(true))

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

  for (const field of [refs.auditLimit, refs.auditTool, refs.auditEvent, refs.auditOk]) {
    field.addEventListener("change", () => {
      syncAuditFiltersFromControls()
      refreshAll(true)
    })
  }

  for (const field of [refs.auditTool, refs.auditEvent]) {
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        syncAuditFiltersFromControls()
        refreshAll(true)
      }
    })
  }

  for (const button of refs.viewTabs) {
    button.addEventListener("click", () => {
      state.activeView = button.dataset.view
      persistView()
      applyActiveView()
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

function syncAuditFiltersFromControls() {
  state.audit = {
    limit: refs.auditLimit.value,
    toolName: refs.auditTool.value.trim(),
    eventType: refs.auditEvent.value.trim(),
    ok: refs.auditOk.value,
  }
  persistAuditFilters()
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

function applyActiveView() {
  for (const button of refs.viewTabs) {
    button.classList.toggle("is-active", button.dataset.view === state.activeView)
  }
  for (const [view, element] of Object.entries(refs.views)) {
    element.classList.toggle("is-active", view === state.activeView)
  }
}

function setActionState() {
  refs.refreshBtn.disabled = state.loading || state.syncing
  refs.syncBtn.disabled = state.syncing
  refs.auditRefreshBtn.disabled = state.loading || state.syncing
  refs.refreshBtn.textContent = state.loading ? "Atualizando..." : "Atualizar"
  refs.syncBtn.textContent = state.syncing ? "Sincronizando..." : "Sincronizar custos"
  refs.auditRefreshBtn.textContent = state.loading ? "Atualizando..." : "Atualizar auditoria"
}

async function refreshAll(manual = false) {
  syncFiltersFromControls()
  syncAuditFiltersFromControls()
  state.loading = true
  setActionState()
  hideGlobalMessage()
  refs.statusLine.textContent = manual
    ? "Atualização manual em andamento."
    : "Atualização automática em andamento."

  try {
    const [overview, costs, tools, health, resilience, auditSummary, auditRecent] = await Promise.all([
      apiGet("/ops/dashboard/overview"),
      apiGet("/ops/dashboard/costs"),
      apiGet("/ops/dashboard/tools"),
      apiGet("/ops/dashboard/health"),
      apiGet("/ops/dashboard/resilience"),
      apiGet("/ops/audit/summary", {
        since_minutes: WINDOW_TO_MINUTES[state.filters.window],
      }),
      apiGet("/ops/audit/recent", {
        limit: state.audit.limit,
        tool_name: state.audit.toolName || undefined,
        event_type: state.audit.eventType || undefined,
        ok: state.audit.ok === "all" ? undefined : state.audit.ok,
      }),
    ])

    renderConsole({
      overview,
      costs,
      tools,
      health,
      resilience,
      auditSummary,
      auditRecent,
    })
    refs.lastRefresh.textContent = `Atualizado às ${new Date().toLocaleTimeString("pt-BR")}`
    refs.statusLine.textContent = "Console operacional atualizada com sucesso."
  } catch (error) {
    if (error.status === 400 && error.detail === "tenant_id obrigatorio em producao") {
      renderTenantRequiredState()
    } else {
      renderFailure(error)
    }
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
      credentials: "same-origin",
    })
    if (!response.ok) {
      const detail = await safeErrorDetail(response)
      throw new Error(`${response.status} ${detail}`)
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

async function apiGet(path, extraParams = {}) {
  const url = new URL(path, window.location.origin)
  url.searchParams.set("window", state.filters.window)
  if (state.filters.tenant) {
    url.searchParams.set("tenant_id", state.filters.tenant)
  }
  if (state.filters.assistant) {
    url.searchParams.set("assistant_id", state.filters.assistant)
  }

  for (const [key, value] of Object.entries(extraParams)) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value)
    }
  }

  const response = await fetch(url, {
    headers: buildHeaders(),
    credentials: "same-origin",
  })
  if (!response.ok) {
    const detail = await safeErrorDetail(response)
    const error = new Error(`${response.status} ${detail}`)
    error.status = response.status
    error.detail = detail
    throw error
  }

  return response.json()
}

async function safeErrorDetail(response) {
  try {
    const payload = await response.json()
    return payload.detail || JSON.stringify(payload)
  } catch (_error) {
    return await response.text()
  }
}

function buildHeaders() {
  if (!bootstrap.token) {
    return {}
  }
  return { [bootstrap.headerName || "x-ops-token"]: bootstrap.token }
}

function renderConsole(model) {
  renderHeaderHealth(model.health)
  renderOverview(model)
  renderDiagnostics(model)
  renderAudit(model)
}

function renderHeaderHealth(health) {
  const { label, className } = mapHealthState(health.health_state)
  refs.healthBadge.className = `health-badge ${className}`
  refs.healthBadge.textContent = label
  refs.healthSummary.textContent = buildHealthSummary(health)
}

function renderOverview(model) {
  const overview = model.overview
  const costs = model.costs
  const tools = model.tools.items
  const totalCalls = Number(overview.kpis.total_calls || 0)
  const successCalls = Number(overview.kpis.success_calls || 0)
  const failedCalls = Number(overview.kpis.failed_calls || 0)
  const handoffCalls = Number(overview.kpis.handoff_calls || 0)
  const successRate = rateOf(successCalls, totalCalls)
  const failureRate = rateOf(failedCalls, totalCalls)
  const handoffRate = rateOf(handoffCalls, totalCalls)
  const coverageRate = rateOf(costs.summary.calls_with_cost, totalCalls)

  refs.total.textContent = numberFmt.format(totalCalls)
  refs.windowLabel.textContent = `Janela ${WINDOW_LABELS[overview.window]}`
  refs.successRate.textContent = formatPercent(successRate)
  refs.successCount.textContent = `${numberFmt.format(successCalls)} calls resolvidas`
  refs.handoffRate.textContent = formatPercent(handoffRate)
  refs.handoffCount.textContent = `${numberFmt.format(handoffCalls)} transferências`
  refs.cost.textContent = formatUsd(costs.summary.total_cost_usd || 0)
  refs.costCalls.textContent = `${numberFmt.format(costs.summary.calls_with_cost || 0)} calls com custo`
  refs.failureRate.textContent = formatPercent(failureRate)
  refs.failureCount.textContent = `${numberFmt.format(failedCalls)} chamadas falhas`
  refs.coverage.textContent = formatPercent(coverageRate)
  refs.coverageMeta.textContent =
    totalCalls > 0
      ? `${numberFmt.format(costs.summary.calls_with_cost || 0)} de ${numberFmt.format(totalCalls)} com custo`
      : "Sem correlação ainda"
  refs.costAvg.textContent = formatUsd(costs.summary.avg_cost_per_call_usd || 0)
  refs.duration.textContent = formatDuration(overview.kpis.avg_duration_ms || 0)

  renderSummaryCards(refs.signalSummary, buildOverviewSignals(model))
  renderFocusCards(refs.focusList, buildOverviewFocusItems(tools))
  renderTimelineList(refs.callsTimeline, overview.series || [], {
    mode: "calls",
    window: state.filters.window,
    emptyText: "Sem buckets de chamadas para a janela atual.",
  })
  renderTimelineList(refs.costTimeline, costs.series || [], {
    mode: "cost",
    window: state.filters.window,
    emptyText: "Nenhum bucket de custo disponível para os filtros atuais.",
  })
  renderToolsTable(tools)
}

function renderDiagnostics(model) {
  const { label } = mapHealthState(model.health.health_state)
  refs.diagHealthState.textContent = label
  refs.diagHealthCopy.textContent = buildHealthSummary(model.health)
  refs.diagSyncState.textContent = formatSyncState(model.health.sync.freshness_state)
  refs.diagSyncAge.textContent = buildSyncAge(model.health.sync)
  refs.diagIdempotencyHits.textContent = numberFmt.format(model.resilience.summary.idempotency_hits || 0)
  refs.diagBusinessErrors.textContent = numberFmt.format(model.resilience.summary.repeated_business_errors || 0)

  renderTimelineList(refs.diagFailedSeries, model.resilience.series.failed_calls || [], {
    mode: "diagnostic",
    window: state.filters.window,
    emptyText: "Nenhum bucket com falha registrada.",
  })
  renderTimelineList(refs.diagIdempotencySeries, model.resilience.series.idempotency_hits || [], {
    mode: "diagnostic",
    window: state.filters.window,
    emptyText: "Nenhum hit de idempotência na janela.",
  })
  renderTimelineList(refs.diagBusinessSeries, model.resilience.series.repeated_business_errors || [], {
    mode: "diagnostic",
    window: state.filters.window,
    emptyText: "Nenhuma repetição de erro de negócio na janela.",
  })

  renderFocusCards(refs.diagTopFailures, buildDiagnosticFocus(model.resilience.top_failure_tools || [], "Falha"))
  renderFocusCards(refs.diagTopHandoffs, buildDiagnosticFocus(model.resilience.top_handoff_tools || [], "Handoff"))
  renderFocusCards(
    refs.diagBusinessTools,
    (model.resilience.business_error_tools || []).map((item) => ({
      label: "Erro repetido",
      title: item.tool_name,
      meta: `${numberFmt.format(item.retries)} repetições`,
      caption: `${numberFmt.format(item.scopes)} escopos afetados.`,
    })),
    "Nenhuma distribuição de erro de negócio encontrada.",
  )
}

function renderAudit(model) {
  const totals = model.auditSummary.totals || {}
  refs.auditTotalCalls.textContent = numberFmt.format(totals.total_calls || 0)
  refs.auditSuccessCalls.textContent = numberFmt.format(totals.success_calls || 0)
  refs.auditFailedCalls.textContent = numberFmt.format(totals.failed_calls || 0)
  refs.auditHandoffCalls.textContent = numberFmt.format(totals.handoff_calls || 0)

  refs.auditTableBody.replaceChildren()
  const items = model.auditRecent.items || []
  refs.auditEmpty.classList.toggle("hidden", items.length > 0)
  for (const item of items) {
    const row = document.createElement("tr")
    appendCell(row, formatDateTime(item.created_at))
    appendCell(row, item.tenant_id || "unknown")
    appendCell(row, item.tool_name || "unknown")
    appendCell(row, item.event_type || "-")
    appendCell(row, item.final_state || "-")
    appendBadgeCell(row, item.ok)
    appendCell(row, item.error_code || "-")
    appendCell(row, formatDuration(item.duration_ms || 0))
    appendCell(row, item.call_id || "-")
    refs.auditTableBody.appendChild(row)
  }
}

function renderTenantRequiredState() {
  showGlobalMessage("Informe um tenant para consultar a console neste ambiente de produção.")
  const health = {
    health_state: "no_data",
    sync: { freshness_state: "unknown", freshness_seconds: null, last_synced_at: null },
    counters: {
      total_calls: 0,
      failed_calls: 0,
      handoff_calls: 0,
      calls_with_cost: 0,
      repeated_business_errors: 0,
      idempotency_hits: 0,
      coverage_pct: 0,
    },
  }
  renderHeaderHealth(health)
  renderOverview({
    overview: { window: state.filters.window, kpis: { total_calls: 0, success_calls: 0, failed_calls: 0, handoff_calls: 0, avg_duration_ms: 0 }, series: [] },
    costs: { summary: { total_cost_usd: 0, calls_with_cost: 0, avg_cost_per_call_usd: 0 }, series: [] },
    tools: { items: [] },
    health,
    resilience: {
      summary: { idempotency_hits: 0, repeated_business_errors: 0 },
      series: { failed_calls: [], idempotency_hits: [], repeated_business_errors: [] },
      top_failure_tools: [],
      top_handoff_tools: [],
      business_error_tools: [],
    },
    auditSummary: { totals: { total_calls: 0, success_calls: 0, failed_calls: 0, handoff_calls: 0 } },
    auditRecent: { items: [] },
  })
}

function renderFailure(error) {
  showGlobalMessage(`Não foi possível carregar a console: ${error.message}`)
  renderHeaderHealth({
    health_state: "critical",
    sync: { freshness_state: "unknown", freshness_seconds: null, last_synced_at: null },
    counters: {
      total_calls: 0,
      failed_calls: 0,
      handoff_calls: 0,
      calls_with_cost: 0,
      repeated_business_errors: 0,
      idempotency_hits: 0,
      coverage_pct: 0,
    },
  })
  renderSummaryCards(refs.signalSummary, [
    {
      label: "Estado da console",
      value: "Erro",
      caption: "A shell carregou, mas os dados operacionais não puderam ser consultados.",
    },
    {
      label: "Próximo passo",
      value: "Revisar acesso",
      caption: "Confirme token, cookie de sessão, banco habilitado e disponibilidade das rotas /ops.",
    },
    {
      label: "Ação sugerida",
      value: "Nova tentativa",
      caption: "Atualize a página após corrigir a conectividade operacional.",
    },
  ])
  renderFocusCards(refs.focusList, [], "Sem destaques enquanto a leitura estiver indisponível.")
  renderTimelineList(refs.callsTimeline, [], {
    mode: "calls",
    window: state.filters.window,
    emptyText: "Sem dados para exibir.",
  })
  renderTimelineList(refs.costTimeline, [], {
    mode: "cost",
    window: state.filters.window,
    emptyText: "Sem dados para exibir.",
  })
  renderToolsTable([])
  refs.diagHealthState.textContent = "Crítico"
  refs.diagHealthCopy.textContent = error.message
  refs.diagSyncState.textContent = "Indisponível"
  refs.diagSyncAge.textContent = "Sem leitura."
  refs.diagIdempotencyHits.textContent = "0"
  refs.diagBusinessErrors.textContent = "0"
  renderTimelineList(refs.diagFailedSeries, [], { mode: "diagnostic", window: state.filters.window, emptyText: "Sem leitura." })
  renderTimelineList(refs.diagIdempotencySeries, [], { mode: "diagnostic", window: state.filters.window, emptyText: "Sem leitura." })
  renderTimelineList(refs.diagBusinessSeries, [], { mode: "diagnostic", window: state.filters.window, emptyText: "Sem leitura." })
  renderFocusCards(refs.diagTopFailures, [], "Sem leitura.")
  renderFocusCards(refs.diagTopHandoffs, [], "Sem leitura.")
  renderFocusCards(refs.diagBusinessTools, [], "Sem leitura.")
  refs.auditTotalCalls.textContent = "0"
  refs.auditSuccessCalls.textContent = "0"
  refs.auditFailedCalls.textContent = "0"
  refs.auditHandoffCalls.textContent = "0"
  refs.auditTableBody.replaceChildren()
  refs.auditEmpty.classList.remove("hidden")
}

function buildOverviewSignals(model) {
  const overview = model.overview
  const health = model.health
  const totalCalls = Number(overview.kpis.total_calls || 0)
  return [
    {
      label: "Saúde da janela",
      value: mapHealthState(health.health_state).label,
      caption: buildHealthSummary(health),
    },
    {
      label: "Cobertura financeira",
      value: totalCalls > 0
        ? `${numberFmt.format(model.costs.summary.calls_with_cost || 0)} / ${numberFmt.format(totalCalls)}`
        : "0 / 0",
      caption: "Calls com custo sincronizado na janela atual.",
    },
    {
      label: "Duração média",
      value: formatDuration(overview.kpis.avg_duration_ms || 0),
      caption: "Tempo médio registrado nas últimas execuções consolidadas.",
    },
  ]
}

function buildOverviewFocusItems(items) {
  if (!items.length) {
    return []
  }
  const topVolume = [...items].sort((left, right) => Number(right.total_calls || 0) - Number(left.total_calls || 0))[0]
  const topFailure = [...items]
    .filter((item) => Number(item.total_calls || 0) > 0)
    .sort((left, right) => Number(right.failure_rate_pct || 0) - Number(left.failure_rate_pct || 0))[0]
  const topCost = [...items].sort((left, right) => Number(right.total_cost_usd || 0) - Number(left.total_cost_usd || 0))[0]
  return [
    topVolume
      ? {
          label: "Maior volume",
          title: topVolume.tool_name,
          meta: `${numberFmt.format(topVolume.total_calls || 0)} calls`,
          caption: "Tool com maior pressão operacional na janela atual.",
        }
      : null,
    topFailure
      ? {
          label: "Maior falha",
          title: topFailure.tool_name,
          meta: formatPercent(topFailure.failure_rate_pct || 0),
          caption: "Maior taxa de falha entre as tools observadas.",
        }
      : null,
    topCost
      ? {
          label: "Maior custo",
          title: topCost.tool_name,
          meta: formatUsd(topCost.total_cost_usd || 0),
          caption: "Maior impacto financeiro agregado na janela.",
        }
      : null,
  ].filter(Boolean)
}

function buildDiagnosticFocus(items, labelPrefix) {
  return items.map((item) => ({
    label: labelPrefix,
    title: item.tool_name,
    meta: labelPrefix === "Handoff"
      ? `${numberFmt.format(item.handoff_calls || 0)} transferências`
      : formatPercent(item.failure_rate_pct || 0),
    caption: `${numberFmt.format(item.total_calls || 0)} execuções observadas.`,
  }))
}

function renderSummaryCards(container, cards) {
  container.replaceChildren()
  for (const card of cards) {
    const article = document.createElement("article")
    article.className = "summary-card"
    article.append(
      buildText("span", "label", card.label),
      buildText("strong", "", card.value),
      buildText("p", "summary-copy", card.caption),
    )
    container.appendChild(article)
  }
}

function renderFocusCards(container, items, emptyText = "Sem dados suficientes para destacar itens nesta janela.") {
  container.replaceChildren()
  if (!items.length) {
    container.appendChild(buildEmptyBlock(emptyText))
    return
  }
  for (const item of items) {
    const article = document.createElement("article")
    article.className = "focus-card"
    article.append(
      buildText("span", "label", item.label),
      buildText("strong", "", item.title),
      buildText("span", "focus-meta", item.meta),
      buildText("p", "", item.caption),
    )
    container.appendChild(article)
  }
}

function renderTimelineList(container, items, options) {
  container.replaceChildren()
  if (!items.length) {
    container.appendChild(buildEmptyBlock(options.emptyText))
    return
  }

  const maxValue = Math.max(
    1,
    ...items.map((item) =>
      options.mode === "calls"
        ? Number(item.calls || 0)
        : options.mode === "cost"
          ? Number(item.cost_usd || 0)
          : Number(item.value || 0),
    ),
  )

  const visible = items.slice(-10)
  for (const item of visible) {
    const row = document.createElement("article")
    row.className = "timeline-row"
    const head = document.createElement("div")
    head.className = "timeline-head"
    const title = buildText("strong", "timeline-title", formatBucket(item.timestamp, options.window))
    let valueText = ""
    let primaryValue = 0
    let secondaryWidth = "0%"
    let segmentClass = "timeline-primary"

    if (options.mode === "calls") {
      const calls = Number(item.calls || 0)
      const handoffs = Number(item.handoffs || 0)
      valueText = `${numberFmt.format(calls)} calls`
      primaryValue = calls
      secondaryWidth = `${calls > 0 ? (handoffs / maxValue) * 100 : 0}%`
    } else if (options.mode === "cost") {
      primaryValue = Number(item.cost_usd || 0)
      valueText = formatUsd(primaryValue)
      segmentClass = "timeline-cost"
    } else {
      primaryValue = Number(item.value || 0)
      valueText = numberFmt.format(primaryValue)
    }

    head.append(title, buildText("span", "timeline-value", valueText))

    const bar = document.createElement("div")
    bar.className = "timeline-bar"
    bar.style.setProperty("--primary-width", `${Math.max((primaryValue / maxValue) * 100, primaryValue > 0 ? 8 : 0)}%`)
    bar.style.setProperty("--secondary-width", secondaryWidth)
    bar.append(
      buildText("div", segmentClass, ""),
      buildText("div", options.mode === "calls" ? "timeline-secondary" : "", ""),
      buildText("div", "", ""),
    )

    const foot = document.createElement("div")
    foot.className = "timeline-foot"
    if (options.mode === "calls") {
      foot.append(
        buildText("span", "", `Handoff ${numberFmt.format(item.handoffs || 0)}`),
        buildText("span", "", `Taxa ${formatPercent(rateOf(item.handoffs || 0, item.calls || 0))}`),
      )
    } else if (options.mode === "cost") {
      foot.append(
        buildText("span", "", `${numberFmt.format(item.calls || 0)} calls`),
        buildText("span", "", Number(item.calls || 0) > 0 ? `${formatUsd((item.cost_usd || 0) / item.calls)} por call` : "Sem custo unitário"),
      )
    } else {
      foot.append(
        buildText("span", "", `${numberFmt.format(primaryValue)} ocorrências`),
        buildText("span", "", "Sinal de resiliência"),
      )
    }

    row.append(head, bar, foot)
    container.appendChild(row)
  }
}

function renderToolsTable(items) {
  refs.toolsTable.replaceChildren()
  refs.tableEmpty.classList.toggle("hidden", items.length > 0)
  for (const item of items) {
    const row = document.createElement("tr")
    appendCell(row, item.tool_name, "tool-name")
    appendCell(row, numberFmt.format(item.total_calls || 0))
    appendCell(row, formatPercent(rateOf(item.success_calls || 0, item.total_calls || 0)))
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

function appendBadgeCell(row, okValue) {
  const cell = document.createElement("td")
  const span = document.createElement("span")
  if (okValue === true) {
    span.className = "pill pill-ok"
    span.textContent = "OK"
  } else if (okValue === false) {
    span.className = "pill pill-fail"
    span.textContent = "Falha"
  } else {
    span.className = "pill"
    span.textContent = "-"
  }
  cell.appendChild(span)
  row.appendChild(cell)
}

function mapHealthState(stateValue) {
  switch (stateValue) {
    case "stable":
      return { label: "Estável", className: "health-stable" }
    case "warning":
      return { label: "Atenção", className: "health-warning" }
    case "critical":
      return { label: "Crítico", className: "health-critical" }
    default:
      return { label: "Sem dados", className: "health-neutral" }
  }
}

function buildHealthSummary(health) {
  const counters = health.counters || {}
  const syncState = formatSyncState(health.sync?.freshness_state)
  return `${numberFmt.format(counters.failed_calls || 0)} falhas, ${numberFmt.format(counters.handoff_calls || 0)} handoffs, cobertura de ${formatPercent(counters.coverage_pct || 0)} e sync ${syncState.toLowerCase()}.`
}

function formatSyncState(syncState) {
  switch (syncState) {
    case "fresh":
      return "Atual"
    case "delayed":
      return "Com atraso"
    case "stale":
      return "Atrasado"
    default:
      return "Desconhecido"
  }
}

function buildSyncAge(sync) {
  if (!sync || sync.freshness_seconds == null) {
    return "Sem histórico de sincronização."
  }
  const minutes = Math.round(sync.freshness_seconds / 60)
  if (minutes < 1) {
    return "Sincronizado há poucos segundos."
  }
  if (minutes < 60) {
    return `Último sync há ${minutes} minuto(s).`
  }
  const hours = (minutes / 60).toFixed(1).replace(".", ",")
  return `Último sync há ${hours} hora(s).`
}

function showGlobalMessage(message) {
  refs.globalMessage.textContent = message
  refs.globalMessage.classList.remove("hidden")
}

function hideGlobalMessage() {
  refs.globalMessage.textContent = ""
  refs.globalMessage.classList.add("hidden")
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

function formatDateTime(timestamp) {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return "-"
  }
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}
