export type WindowKey = "15m" | "1h" | "24h" | "7d"
export type HealthState = "stable" | "warning" | "critical" | "no_data" | string

export type DashboardFilters = {
  window: WindowKey
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
  }
  counters: {
    totalCalls: number
    failedCalls: number
    handoffCalls: number
    callsWithCost: number
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
  }
  series: Array<{
    timestamp: string
    calls: number
    handoffs: number
  }>
}

export type Costs = {
  summary: {
    totalCostUsd: number
    callsWithCost: number
    avgCostPerCallUsd: number
  }
  series: Array<{
    timestamp: string
    calls: number
    costUsd: number
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
  uniqueCalls: number
  totalCostUsd: number
  avgCostPerCallUsd: number
}

export type Resilience = {
  healthState: HealthState
  sync: Health["sync"]
  summary: {
    totalCalls: number
    failedCalls: number
    handoffCalls: number
    repeatedBusinessErrors: number
    idempotencyHits: number
  }
  series: {
    failedCalls: ResiliencePoint[]
    idempotencyHits: ResiliencePoint[]
    repeatedBusinessErrors: ResiliencePoint[]
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
  }
}
