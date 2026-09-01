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
  cache: {
    health: null,
    overview: null,
    diagnostics: null,
    audit: null,
  },
  requestSeq: 0,
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
  overviewHeroCopy: document.getElementById("overview-hero-copy"),
  overviewHeroStat: document.getElementById("overview-hero-stat"),
  overviewHeroMeta: document.getElementById("overview-hero-meta"),
  diagHeroCopy: document.getElementById("diag-hero-copy"),
  auditHeroCopy: document.getElementById("audit-hero-copy"),
  auditHeroStat: document.getElementById("audit-hero-stat"),
  auditHeroMeta: document.getElementById("audit-hero-meta"),
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
  durationMeta: document.getElementById("k-duration-meta"),
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
  diagCoverage: document.getElementById("diag-coverage"),
  diagCoverageCopy: document.getElementById("diag-coverage-copy"),
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
renderHeaderHealth(emptyHealthModel())
renderOverview(emptyOverviewModel())
renderDiagnostics(emptyDiagnosticsModel())
renderAudit(emptyAuditModel())
refreshActiveView()
window.setInterval(() => refreshActiveView(false), bootstrap.refreshIntervalMs || 45_000)

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
  refs.refreshBtn.addEventListener("click", () => refreshActiveView(true, true))
  refs.syncBtn.addEventListener("click", syncCosts)
  refs.auditRefreshBtn.addEventListener("click", () => refreshActiveView(true, true))

  refs.window.addEventListener("change", handleFilterMutation)

  for (const field of [refs.tenant, refs.assistant]) {
    field.addEventListener("change", handleFilterMutation)
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        handleFilterMutation()
      }
    })
  }

  for (const field of [refs.auditLimit, refs.auditTool, refs.auditEvent, refs.auditOk]) {
    field.addEventListener("change", handleAuditFilterMutation)
  }

  for (const field of [refs.auditTool, refs.auditEvent]) {
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        handleAuditFilterMutation()
      }
    })
  }

  for (const button of refs.viewTabs) {
    button.addEventListener("click", () => {
      state.activeView = button.dataset.view
      persistView()
      applyActiveView()
      applyContextText()
      renderActiveViewFromCache()
      if (!hasDataForView(state.activeView)) {
        refreshActiveView(false, true)
      }
    })
  }
}

function handleFilterMutation() {
  syncFiltersFromControls()
  invalidateViewCache()
  refreshActiveView(true, true)
}

function handleAuditFilterMutation() {
  syncAuditFiltersFromControls()
  state.cache.audit = null
  if (state.activeView === "audit") {
    refreshActiveView(true, true)
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

function invalidateViewCache() {
  state.cache.health = null
  state.cache.overview = null
  state.cache.diagnostics = null
  state.cache.audit = null
}

function applyContextText() {
  const parts = [`Janela ${WINDOW_LABELS[state.filters.window]}`]
  if (state.filters.tenant) {
    parts.push(`tenant ${state.filters.tenant}`)
  } else {
    parts.push(viewName(state.activeView).toLowerCase())
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

function renderActiveViewFromCache() {
  if (state.cache.health) {
    renderHeaderHealth(state.cache.health)
  }

  if (state.activeView === "overview") {
    renderOverview(state.cache.overview || emptyOverviewModel())
  } else if (state.activeView === "diagnostics") {
    renderDiagnostics(state.cache.diagnostics || emptyDiagnosticsModel())
  } else {
    renderAudit(state.cache.audit || emptyAuditModel())
  }
}

function hasDataForView(view) {
  if (view === "overview") {
    return Boolean(state.cache.overview)
  }
  if (view === "diagnostics") {
    return Boolean(state.cache.diagnostics)
  }
  return Boolean(state.cache.audit)
}

async function refreshActiveView(manual = false, force = false) {
  syncFiltersFromControls()
  syncAuditFiltersFromControls()

  if (state.loading && !force) {
    return
  }

  state.loading = true
  const requestId = ++state.requestSeq
  setActionState()
  hideGlobalMessage()
  refs.statusLine.textContent = manual
    ? `Atualização manual da ${viewName(state.activeView).toLowerCase()} em andamento.`
    : `Atualização da ${viewName(state.activeView).toLowerCase()} em andamento.`

  try {
    const model = await fetchViewBundle(state.activeView)
    if (requestId !== state.requestSeq) {
      return
    }

    state.cache.health = model.health
    if (state.activeView === "overview") {
      state.cache.overview = model.overview
      renderOverview(model.overview)
    } else if (state.activeView === "diagnostics") {
      state.cache.diagnostics = model.diagnostics
      renderDiagnostics(model.diagnostics)
    } else {
      state.cache.audit = model.audit
      renderAudit(model.audit)
    }

    renderHeaderHealth(model.health)
    refs.lastRefresh.textContent = `Atualizado às ${new Date().toLocaleTimeString("pt-BR")}`
    refs.statusLine.textContent = `${viewName(state.activeView)} carregada com sucesso.`
  } catch (error) {
    if (requestId !== state.requestSeq) {
      return
    }
    if (isTenantRequiredError(error)) {
      renderTenantRequiredState()
    } else {
      renderFailure(error)
    }
    refs.lastRefresh.textContent = "Falha ao atualizar"
    refs.statusLine.textContent = `Falha ao carregar dados: ${error.message}`
  } finally {
    if (requestId === state.requestSeq) {
      state.loading = false
      setActionState()
    }
  }
}

async function fetchViewBundle(view) {
  if (view === "overview") {
    const [health, overview, costs, tools] = await Promise.all([
      apiGet("/ops/dashboard/health"),
      apiGet("/ops/dashboard/overview"),
      apiGet("/ops/dashboard/costs"),
      apiGet("/ops/dashboard/tools"),
    ])
    return {
      health,
      overview: {
        overview,
        costs,
        tools: tools.items || [],
        health,
      },
    }
  }

  if (view === "diagnostics") {
    const [health, resilience] = await Promise.all([
      apiGet("/ops/dashboard/health"),
      apiGet("/ops/dashboard/resilience"),
    ])
    return {
      health,
      diagnostics: {
        health,
        resilience,
      },
    }
  }

  const [health, auditSummary, auditRecent] = await Promise.all([
    apiGet("/ops/dashboard/health"),
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
  return {
    health,
    audit: {
      health,
      auditSummary,
      auditRecent,
    },
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
    invalidateViewCache()
    await refreshActiveView(true, true)
  } catch (error) {
    refs.statusLine.textContent = `Sync falhou: ${error.message}`
    showGlobalMessage(`Não foi possível sincronizar os custos: ${error.message}`)
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

function isTenantRequiredError(error) {
  return error.status === 400 && error.detail === "tenant_id obrigatorio em producao"
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
  const tools = model.tools
  const health = model.health
  const totalCalls = Number(overview.kpis.total_calls || 0)
  const automatedResolutionCalls = Number(overview.kpis.automated_resolution_calls || 0)
  const successfulHandoffCalls = Number(overview.kpis.successful_handoff_calls || 0)
  const successfulAgentCalls = Number(overview.kpis.successful_agent_calls || 0)
  const technicalFailureEvents = Number(overview.kpis.technical_failure_events || 0)
  const toolExecutionCount = Number(overview.kpis.tool_execution_count || 0)
  const successRate = Number(overview.kpis.agent_success_rate_pct || rateOf(successfulAgentCalls, totalCalls))
  const failureRate = rateOf(technicalFailureEvents, toolExecutionCount)
  const handoffRate = rateOf(successfulHandoffCalls, totalCalls)
  const coverageRate = rateOf(costs.summary.calls_with_cost, totalCalls)

  refs.total.textContent = numberFmt.format(totalCalls)
  refs.windowLabel.textContent = `Janela ${WINDOW_LABELS[overview.window]}`
  refs.successRate.textContent = formatPercent(successRate)
  refs.successCount.textContent = `${numberFmt.format(successfulAgentCalls)} calls resolvidas ou transferidas`
  refs.handoffRate.textContent = formatPercent(handoffRate)
  refs.handoffCount.textContent = `${numberFmt.format(successfulHandoffCalls)} transferências iniciadas`
  refs.cost.textContent = formatUsd(costs.summary.total_cost_usd || 0)
  refs.costCalls.textContent = `${numberFmt.format(costs.summary.calls_with_cost || 0)} calls com custo`
  refs.failureRate.textContent = formatPercent(failureRate)
  refs.failureCount.textContent = `${numberFmt.format(technicalFailureEvents)} falhas em ${numberFmt.format(toolExecutionCount)} execuções`
  refs.coverage.textContent = formatPercent(coverageRate)
  refs.coverageMeta.textContent =
    totalCalls > 0
      ? `${numberFmt.format(costs.summary.calls_with_cost || 0)} de ${numberFmt.format(totalCalls)} com custo`
      : "Sem correlação ainda"
  refs.costAvg.textContent = formatUsd(costs.summary.avg_cost_per_call_usd || 0)
  refs.duration.textContent = formatDurationSeconds(costs.summary.avg_duration_seconds || 0)
  refs.durationMeta.textContent =
    `${numberFmt.format(costs.summary.calls_with_duration || 0)} calls com duração | total ${formatDurationSeconds(costs.summary.total_duration_seconds || 0)}`

  refs.overviewHeroCopy.textContent = totalCalls > 0
    ? `A janela atual registrou ${numberFmt.format(totalCalls)} calls com ${formatPercent(successRate)} de sucesso do agente, incluindo ${formatPercent(handoffRate)} de sucesso com handoff e ${numberFmt.format(automatedResolutionCalls)} resoluções automáticas.`
    : "Nenhuma call encontrada para os filtros atuais."
  refs.overviewHeroStat.textContent = mapHealthState(health.health_state).label
  refs.overviewHeroMeta.textContent = buildHealthSummary(health)

  renderSummaryCards(refs.signalSummary, buildOverviewSignals(model))
  renderFocusCards(refs.focusList, buildOverviewFocusItems(tools))
  renderTimelineList(refs.callsTimeline, overview.series || [], {
    mode: "calls",
    window: overview.window,
    emptyText: "Sem buckets de chamadas para a janela atual.",
  })
  renderTimelineList(refs.costTimeline, costs.series || [], {
    mode: "cost",
    window: overview.window,
    emptyText: "Nenhum bucket de custo disponível para os filtros atuais.",
  })
  renderToolsTable(tools)
}

function renderDiagnostics(model) {
  const { health, resilience } = model
  const counters = health.counters || {}

  refs.diagHeroCopy.textContent = buildDiagnosticHeroCopy(health, resilience)
  refs.diagHealthState.textContent = mapHealthState(health.health_state).label
  refs.diagHealthCopy.textContent = buildHealthSummary(health)
  refs.diagSyncState.textContent = formatSyncState(health.sync?.freshness_state)
  refs.diagSyncAge.textContent = buildSyncAge(health.sync)
  refs.diagIdempotencyHits.textContent = numberFmt.format(resilience.summary.idempotency_hits || 0)
  refs.diagBusinessErrors.textContent = numberFmt.format(resilience.summary.repeated_business_errors || 0)
  refs.diagCoverage.textContent = formatPercent(counters.coverage_pct || 0)
  refs.diagCoverageCopy.textContent = counters.total_calls > 0
    ? `${numberFmt.format(counters.calls_with_cost || 0)} de ${numberFmt.format(counters.total_calls || 0)} calls com custo associado.`
    : "Sem correlação suficiente."

  renderTimelineList(refs.diagFailedSeries, resilience.series.technical_failure_events || [], {
    mode: "diagnostic",
    window: state.filters.window,
    emptyText: "Nenhum bucket com falha técnica registrada.",
  })
  renderTimelineList(refs.diagIdempotencySeries, resilience.series.idempotency_hits || [], {
    mode: "diagnostic",
    window: state.filters.window,
    emptyText: "Nenhum hit de idempotência na janela.",
  })
  renderTimelineList(refs.diagBusinessSeries, resilience.series.repeated_business_errors || [], {
    mode: "diagnostic",
    window: state.filters.window,
    emptyText: "Nenhuma repetição de erro de negócio na janela.",
  })

  renderFocusCards(refs.diagTopFailures, buildDiagnosticFocus(resilience.top_failure_tools || [], "Falha técnica"))
  renderFocusCards(refs.diagTopHandoffs, buildDiagnosticFocus(resilience.top_handoff_tools || [], "Handoff"))
  renderFocusCards(
    refs.diagBusinessTools,
    (resilience.business_error_tools || []).map((item) => ({
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
  const recentItems = model.auditRecent.items || []

  refs.auditHeroCopy.textContent = totals.total_calls > 0
    ? `A trilha recente reúne ${numberFmt.format(totals.total_calls)} chamadas auditadas na janela.`
    : "Nenhuma chamada auditada encontrada para os filtros atuais."
  refs.auditHeroStat.textContent = recentItems.length > 0 ? "Trilha disponível" : "Sem eventos"
  refs.auditHeroMeta.textContent = recentItems.length > 0
    ? `${numberFmt.format(recentItems.length)} eventos retornados nesta consulta.`
    : "Ajuste os filtros para ampliar a busca."

  refs.auditTotalCalls.textContent = numberFmt.format(totals.total_calls || 0)
  refs.auditSuccessCalls.textContent = numberFmt.format(totals.success_calls || 0)
  refs.auditFailedCalls.textContent = numberFmt.format(totals.technical_failure_events || 0)
  refs.auditHandoffCalls.textContent = numberFmt.format(totals.handoff_calls || 0)

  refs.auditTableBody.replaceChildren()
  refs.auditEmpty.classList.toggle("hidden", recentItems.length > 0)
  for (const item of recentItems) {
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
  const health = emptyHealthModel()
  renderHeaderHealth(health)
  renderOverview(emptyOverviewModel())
  renderDiagnostics(emptyDiagnosticsModel())
  renderAudit(emptyAuditModel())
  refs.overviewHeroCopy.textContent = "Defina um tenant para carregar a visão geral em produção."
  refs.diagHeroCopy.textContent = "Defina um tenant para carregar o diagnóstico em produção."
  refs.auditHeroCopy.textContent = "Defina um tenant para carregar a auditoria em produção."
}

function renderFailure(error) {
  showGlobalMessage(`Não foi possível carregar a console: ${error.message}`)
  renderHeaderHealth({ ...emptyHealthModel(), health_state: "critical" })
  renderOverview(emptyOverviewModel())
  renderDiagnostics(emptyDiagnosticsModel())
  renderAudit(emptyAuditModel())
  refs.overviewHeroCopy.textContent = "A shell carregou, mas a visão geral não pôde ser consultada."
  refs.diagHeroCopy.textContent = "O diagnóstico está indisponível até a conectividade operacional ser restabelecida."
  refs.auditHeroCopy.textContent = "A trilha de auditoria não pôde ser carregada."
  refs.auditHeroStat.textContent = "Erro"
  refs.auditHeroMeta.textContent = "Revise token, cookie de sessão, banco e rotas /ops."
  refs.diagHealthState.textContent = "Crítico"
  refs.diagHealthCopy.textContent = error.message
}

function buildOverviewSignals(model) {
  const { overview, costs, health } = model
  const totalCalls = Number(overview.kpis.total_calls || 0)
  return [
    {
      label: "Saúde da janela",
      value: mapHealthState(health.health_state).label,
      caption: buildHealthSummary(health),
    },
    {
      label: "Cobertura de custo",
      value: totalCalls > 0
        ? `${numberFmt.format(costs.summary.calls_with_cost || 0)} / ${numberFmt.format(totalCalls)}`
        : "0 / 0",
      caption: "Calls com custo sincronizado na janela atual.",
    },
    {
      label: "Tempo médio de ligação",
      value: formatDurationSeconds(costs.summary.avg_duration_seconds || 0),
      caption: "Base nas calls Vapi sincronizadas com duração.",
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
    .sort((left, right) => Number(right.technical_failure_rate_pct || 0) - Number(left.technical_failure_rate_pct || 0))[0]
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
          label: "Maior falha técnica",
          title: topFailure.tool_name,
          meta: formatPercent(topFailure.technical_failure_rate_pct || 0),
          caption: "Maior taxa de falha técnica entre as tools observadas.",
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
      : formatPercent(item.technical_failure_rate_pct || 0),
    caption: `${numberFmt.format(item.total_calls || 0)} execuções observadas.`,
  }))
}

function buildDiagnosticHeroCopy(health, resilience) {
  const counters = health.counters || {}
  if (!counters.total_calls) {
    return "Sem volume suficiente para avaliar robustez na janela atual."
  }
  return `${numberFmt.format(counters.technical_failure_events || 0)} falhas técnicas, ${numberFmt.format(resilience.summary.repeated_business_errors || 0)} erros repetidos e ${numberFmt.format(resilience.summary.idempotency_hits || 0)} reaproveitamentos registrados.`
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

  const visible = items.slice(-8)
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
      const handoffs = Number(item.successful_handoffs ?? item.handoffs ?? 0)
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
        buildText("span", "", `Handoff ${numberFmt.format(item.successful_handoffs ?? item.handoffs ?? 0)}`),
        buildText("span", "", `Taxa ${formatPercent(rateOf(item.successful_handoffs ?? item.handoffs ?? 0, item.calls || 0))}`),
      )
    } else if (options.mode === "cost") {
      foot.append(
        buildText("span", "", `${numberFmt.format(item.calls || 0)} calls`),
        buildText("span", "", Number(item.duration_seconds || 0) > 0 ? `${formatDurationSeconds(item.duration_seconds)} de ligação` : "Sem duração"),
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
    appendCell(row, formatPercent(item.technical_failure_rate_pct || 0))
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
  return `${numberFmt.format(counters.technical_failure_events || 0)} falhas técnicas, ${numberFmt.format(counters.handoff_calls || 0)} handoffs, cobertura de ${formatPercent(counters.coverage_pct || 0)} e sync ${syncState.toLowerCase()}.`
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

function emptyHealthModel() {
  return {
    health_state: "no_data",
    sync: {
      freshness_state: "unknown",
      freshness_seconds: null,
      last_synced_at: null,
    },
    counters: {
      total_calls: 0,
      failed_calls: 0,
      handoff_calls: 0,
      technical_failure_events: 0,
      calls_with_cost: 0,
      repeated_business_errors: 0,
      idempotency_hits: 0,
      coverage_pct: 0,
    },
  }
}

function emptyOverviewModel() {
  return {
    overview: {
      window: state.filters.window,
      kpis: {
        total_calls: 0,
        success_calls: 0,
        failed_calls: 0,
        handoff_calls: 0,
        avg_duration_ms: 0,
        automated_resolution_calls: 0,
        successful_handoff_calls: 0,
        successful_agent_calls: 0,
        agent_success_rate_pct: 0,
        unresolved_calls: 0,
        technical_failure_events: 0,
        tool_execution_count: 0,
      },
      series: [],
    },
    costs: {
      summary: {
        total_cost_usd: 0,
        calls_with_cost: 0,
        avg_cost_per_call_usd: 0,
        calls_with_duration: 0,
        total_duration_seconds: 0,
        avg_duration_seconds: 0,
      },
      series: [],
    },
    tools: [],
    health: state.cache.health || emptyHealthModel(),
  }
}

function emptyDiagnosticsModel() {
  return {
    health: state.cache.health || emptyHealthModel(),
    resilience: {
      summary: {
        idempotency_hits: 0,
        repeated_business_errors: 0,
      },
      series: {
        failed_calls: [],
        technical_failure_events: [],
        idempotency_hits: [],
        repeated_business_errors: [],
      },
      top_failure_tools: [],
      top_handoff_tools: [],
      business_error_tools: [],
    },
  }
}

function emptyAuditModel() {
  return {
    health: state.cache.health || emptyHealthModel(),
    auditSummary: {
      totals: {
        total_calls: 0,
        success_calls: 0,
        failed_calls: 0,
        handoff_calls: 0,
        technical_failure_events: 0,
      },
    },
    auditRecent: {
      items: [],
    },
  }
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

function formatDurationSeconds(value) {
  const seconds = Number(value || 0)
  if (seconds >= 3600) {
    return `${(seconds / 3600).toFixed(1).replace(".", ",")} h`
  }
  if (seconds >= 60) {
    return `${(seconds / 60).toFixed(1).replace(".", ",")} min`
  }
  return `${Math.round(seconds)} s`
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

function viewName(view) {
  switch (view) {
    case "diagnostics":
      return "Diagnóstico"
    case "audit":
      return "Auditoria"
    default:
      return "Visão Geral"
  }
}
