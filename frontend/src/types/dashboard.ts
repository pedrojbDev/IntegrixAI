export type WindowKey = "15m" | "1h" | "24h" | "7d" | "30d" | "60d" | "90d" | "custom"
export type ReportPeriodDays = 7 | 15 | 30 | 90
export type HealthState = "stable" | "warning" | "critical" | "no_data" | string
export type OpsRole = "platform_admin" | "tenant_user"

export type SessionPrincipal = {
  id: string
  email: string
  role: OpsRole
  tenantIds: string[]
  mustChangePassword: boolean
}

export type OpsUser = SessionPrincipal & {
  isActive: boolean
  createdAt: string
  updatedAt: string
}

export type DashboardFilters = {
  window: WindowKey
  startDate?: string
  endDate?: string
  tenantId?: string
  assistantId?: string
}

export type AuditFilters = {
  limit: number
  toolName?: string
  eventType?: string
  ok?: "true" | "false"
}

export type Health = {
  window: WindowKey
  healthState: HealthState
  sync: {
    lastSyncedAt: string | null
    freshnessSeconds: number | null
    freshnessState: string
    lastError: string | null
    consecutiveFailures: number
    lastRunStats: {
      processed: number
      created: number
      updated: number
      missingCost: number
      unresolvedTenant: number
      missingFx: number
      errors: number
    } | null
  }
  counters: {
    totalCalls: number
    vapiCalls: number
    failedCalls: number
    handoffCalls: number
    technicalFailureEvents: number
    technicalFailureRatePct: number
    toolExecutionCount: number
    callsWithCost: number
    callsWithoutCost: number
    repeatedBusinessErrors: number
    idempotencyHits: number
    coveragePct: number
  }
  topDegradingTools: ToolPerformance[]
}

export type Overview = {
  window: WindowKey
  since: string | null
  kpis: {
    totalCalls: number
    successCalls: number
    failedCalls: number
    handoffCalls: number
    avgDurationMs: number
    automatedResolutionCalls: number
    successfulHandoffCalls: number
    normalCompletionCalls: number
    successfulAgentCalls: number
    agentSuccessRatePct: number
    unresolvedCalls: number
    technicalFailureEvents: number
    toolExecutionCount: number
    technicalFailureRatePct: number
  }
  series: Array<{
    timestamp: string
    calls: number
    handoffs: number
    successfulHandoffs: number
    automatedResolutions: number
    normalCompletions: number
    unresolvedCalls: number
  }>
}

export type Costs = {
  visibility: "enabled" | "admin_preview" | "hidden"
  summary: {
    totalCostUsd: number
    totalCostBrl: number | null
    vapiCalls: number
    callsWithCost: number
    callsWithoutCost: number
    coveragePct: number
    avgCostPerCallUsd: number
    avgCostPerCallBrl: number | null
    callsWithDuration: number
    totalDurationSeconds: number
    avgDurationSeconds: number
  }
  series: Array<{
    timestamp: string
    calls: number
    costUsd: number
    costBrl: number | null
    durationSeconds: number
    provisionalCalls: number
  }>
  fx: {
    source: string
    complete: boolean
    provisionalCalls: number
    missingRateCalls: number
    lastRateDate: string | null
  }
  reconciliation: {
    operationalCalls: number
    linkedOperationalCalls: number
    linkageCoveragePct: number
    componentAdjustmentCalls: number
  }
  breakdown: Array<{
    category: string
    costUsd: number
    sharePct: number
  }>
}

export type ToolPerformance = {
  toolName: string
  totalCalls: number
  successCalls: number
  failedCalls: number
  handoffCalls: number
  avgDurationMs: number
  failureRatePct: number
  technicalFailureEvents: number
  technicalFailureRatePct: number
  uniqueCalls: number
}

export type Resilience = {
  healthState: HealthState
  sync: Health["sync"]
  summary: {
    totalCalls: number
    failedCalls: number
    handoffCalls: number
    technicalFailureEvents: number
    technicalFailureRatePct: number
    repeatedBusinessErrors: number
    idempotencyHits: number
  }
  searchFunnel: {
    attemptedCalls: number
    blockedCalls: number
    upstreamStartedCalls: number
    completedCalls: number
    providerResultCalls: number
    reusedResultCalls: number
  }
  slotBlocks: {
    cpf: number
    city: number
    specialty: number
    waitingForNewTurn: number
  }
  upstreamFailures: {
    auth: number
    timeout: number
    network: number
    fiveXx: number
    unexpected: number
  }
  handoffFlow: {
    recommendations: number
    nativeTransfers: number
  }
  voiceQuality: {
    callsWithMetrics: number
    averageTurnLatencyMs: number | null
    totalAssistantInterruptions: number
    callsWithAssistantInterruptions: number
  }
  series: {
    failedCalls: ResiliencePoint[]
    technicalFailureEvents: ResiliencePoint[]
    idempotencyHits: ResiliencePoint[]
    repeatedBusinessErrors: ResiliencePoint[]
    blocks: ResiliencePoint[]
    successes: ResiliencePoint[]
    externalFailures: ResiliencePoint[]
    turnLatencyAverageMs: ResiliencePoint[]
    assistantInterruptions: ResiliencePoint[]
  }
  topFailureTools: ToolPerformance[]
  topHandoffTools: ToolPerformance[]
  businessErrorTools: Array<{
    toolName: string
    retries: number
    scopes: number
  }>
}

export type ResiliencePoint = {
  timestamp: string
  value: number
}

export type AuditSummary = {
  totals: {
    totalCalls: number
    successCalls: number
    failedCalls: number
    handoffCalls: number
    technicalFailureEvents: number
    avgDurationMs: number
  }
}

export type AuditEvent = {
  id: number | string
  tenantId: string
  callId: string
  toolName: string
  eventType: string
  finalState: string
  ok: boolean | null
  durationMs: number
  errorCode: string | null
  createdAt: string
}

export type CostSyncResult = {
  ok: boolean
  result: {
    processed: number
    created: number
    updated: number
    missingCost: number
    unresolvedTenant: number
    missingFx: number
    errors: number
    locked: boolean
  }
}
