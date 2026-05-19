import type {
  AuditEvent,
  AuditSummary,
  CostSyncResult,
  Costs,
  Health,
  Overview,
  Resilience,
  ToolPerformance,
} from "@/types/dashboard"

import type {
  auditRecentSchema,
  auditSummarySchema,
  costsSchema,
  costSyncSchema,
  healthSchema,
  overviewSchema,
  resilienceSchema,
  toolPerformanceSchema,
} from "./schemas"
import type { z } from "zod"

type RawTool = z.infer<typeof toolPerformanceSchema>
type RawHealth = z.infer<typeof healthSchema>
type RawOverview = z.infer<typeof overviewSchema>
type RawCosts = z.infer<typeof costsSchema>
type RawResilience = z.infer<typeof resilienceSchema>
type RawAuditSummary = z.infer<typeof auditSummarySchema>
type RawAuditRecent = z.infer<typeof auditRecentSchema>
type RawCostSync = z.infer<typeof costSyncSchema>

export function mapTool(raw: RawTool): ToolPerformance {
  return {
    toolName: raw.tool_name,
    totalCalls: raw.total_calls,
    successCalls: raw.success_calls,
    failedCalls: raw.failed_calls,
    handoffCalls: raw.handoff_calls,
    avgDurationMs: raw.avg_duration_ms,
    failureRatePct: raw.failure_rate_pct,
    uniqueCalls: raw.unique_calls,
    totalCostUsd: raw.total_cost_usd,
    avgCostPerCallUsd: raw.avg_cost_per_call_usd,
  }
}

export function mapHealth(raw: RawHealth): Health {
  return {
    window: raw.window,
    healthState: raw.health_state,
    sync: {
      lastSyncedAt: raw.sync.last_synced_at,
      freshnessSeconds: raw.sync.freshness_seconds,
      freshnessState: raw.sync.freshness_state,
    },
    counters: {
      totalCalls: raw.counters.total_calls,
      failedCalls: raw.counters.failed_calls,
      handoffCalls: raw.counters.handoff_calls,
      callsWithCost: raw.counters.calls_with_cost,
      repeatedBusinessErrors: raw.counters.repeated_business_errors,
      idempotencyHits: raw.counters.idempotency_hits,
      coveragePct: raw.counters.coverage_pct,
    },
    topDegradingTools: raw.top_degrading_tools.map(mapTool),
  }
}

export function mapOverview(raw: RawOverview): Overview {
  return {
    window: raw.window,
    since: raw.since,
    kpis: {
      totalCalls: raw.kpis.total_calls,
      successCalls: raw.kpis.success_calls,
      failedCalls: raw.kpis.failed_calls,
      handoffCalls: raw.kpis.handoff_calls,
      avgDurationMs: raw.kpis.avg_duration_ms,
    },
    series: raw.series.map((point) => ({
      timestamp: point.timestamp,
      calls: point.calls || 0,
      handoffs: point.handoffs || 0,
    })),
  }
}

export function mapCosts(raw: RawCosts): Costs {
  return {
    summary: {
      totalCostUsd: raw.summary.total_cost_usd,
      callsWithCost: raw.summary.calls_with_cost,
      avgCostPerCallUsd: raw.summary.avg_cost_per_call_usd,
    },
    series: raw.series.map((point) => ({
      timestamp: point.timestamp,
      calls: point.calls,
      costUsd: point.cost_usd,
    })),
  }
}

export function mapResilience(raw: RawResilience): Resilience {
  return {
    healthState: raw.health_state,
    sync: {
      lastSyncedAt: raw.sync.last_synced_at,
      freshnessSeconds: raw.sync.freshness_seconds,
      freshnessState: raw.sync.freshness_state,
    },
    summary: {
      totalCalls: raw.summary.total_calls,
      failedCalls: raw.summary.failed_calls,
      handoffCalls: raw.summary.handoff_calls,
      repeatedBusinessErrors: raw.summary.repeated_business_errors,
      idempotencyHits: raw.summary.idempotency_hits,
    },
    series: {
      failedCalls: raw.series.failed_calls.map((point) => ({
        timestamp: point.timestamp,
        value: point.value || 0,
      })),
      idempotencyHits: raw.series.idempotency_hits.map((point) => ({
        timestamp: point.timestamp,
        value: point.value || 0,
      })),
      repeatedBusinessErrors: raw.series.repeated_business_errors.map((point) => ({
        timestamp: point.timestamp,
        value: point.value || 0,
      })),
    },
    topFailureTools: raw.top_failure_tools.map(mapTool),
    topHandoffTools: raw.top_handoff_tools.map(mapTool),
    businessErrorTools: raw.business_error_tools.map((item) => ({
      toolName: item.tool_name,
      retries: item.retries,
      scopes: item.scopes,
    })),
  }
}

export function mapAuditSummary(raw: RawAuditSummary): AuditSummary {
  return {
    totals: {
      totalCalls: raw.totals.total_calls,
      successCalls: raw.totals.success_calls,
      failedCalls: raw.totals.failed_calls,
      handoffCalls: raw.totals.handoff_calls,
      avgDurationMs: raw.totals.avg_duration_ms,
    },
  }
}

export function mapAuditEvents(raw: RawAuditRecent): AuditEvent[] {
  return raw.items.map((item) => ({
    id: item.id,
    tenantId: item.tenant_id || "unknown",
    callId: item.call_id || "-",
    toolName: item.tool_name || "unknown",
    eventType: item.event_type || "-",
    finalState: item.final_state || "-",
    ok: item.ok,
    durationMs: item.duration_ms,
    errorCode: item.error_code,
    createdAt: item.created_at,
  }))
}

export function mapCostSync(raw: RawCostSync): CostSyncResult {
  return {
    ok: raw.ok,
    result: {
      processed: raw.result.processed || 0,
      created: raw.result.created || 0,
    },
  }
}
