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
    technicalFailureEvents: raw.technical_failure_events,
    technicalFailureRatePct: raw.technical_failure_rate_pct,
    uniqueCalls: raw.unique_calls,
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
      lastError: raw.sync.last_error,
      consecutiveFailures: raw.sync.consecutive_failures,
      lastRunStats: raw.sync.last_run_stats
        ? {
            processed: raw.sync.last_run_stats.processed,
            created: raw.sync.last_run_stats.created,
            updated: raw.sync.last_run_stats.updated,
            missingCost: raw.sync.last_run_stats.missing_cost,
            unresolvedTenant: raw.sync.last_run_stats.unresolved_tenant,
            missingFx: raw.sync.last_run_stats.missing_fx,
            errors: raw.sync.last_run_stats.errors,
          }
        : null,
    },
    counters: {
      totalCalls: raw.counters.total_calls,
      vapiCalls: raw.counters.vapi_calls,
      failedCalls: raw.counters.failed_calls,
      handoffCalls: raw.counters.handoff_calls,
      technicalFailureEvents: raw.counters.technical_failure_events,
      technicalFailureRatePct: raw.counters.technical_failure_rate_pct,
      toolExecutionCount: raw.counters.tool_execution_count,
      callsWithCost: raw.counters.calls_with_cost,
      callsWithoutCost: raw.counters.calls_without_cost,
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
      automatedResolutionCalls: raw.kpis.automated_resolution_calls,
      successfulHandoffCalls: raw.kpis.successful_handoff_calls,
      normalCompletionCalls: raw.kpis.normal_completion_calls,
      successfulAgentCalls: raw.kpis.successful_agent_calls,
      agentSuccessRatePct: raw.kpis.agent_success_rate_pct,
      unresolvedCalls: raw.kpis.unresolved_calls,
      technicalFailureEvents: raw.kpis.technical_failure_events,
      toolExecutionCount: raw.kpis.tool_execution_count,
      technicalFailureRatePct: raw.kpis.technical_failure_rate_pct,
    },
    series: raw.series.map((point) => ({
      timestamp: point.timestamp,
      calls: point.calls || 0,
      handoffs: point.handoffs || 0,
      successfulHandoffs: point.successful_handoffs || 0,
      automatedResolutions: point.automated_resolutions || 0,
      normalCompletions: point.normal_completions || 0,
      unresolvedCalls: point.unresolved_calls || 0,
    })),
  }
}

export function mapCosts(raw: RawCosts): Costs {
  return {
    visibility: raw.visibility,
    summary: {
      totalCostUsd: raw.summary.total_cost_usd,
      totalCostBrl: raw.summary.total_cost_brl,
      vapiCalls: raw.summary.vapi_calls,
      callsWithCost: raw.summary.calls_with_cost,
      callsWithoutCost: raw.summary.calls_without_cost,
      coveragePct: raw.summary.coverage_pct,
      avgCostPerCallUsd: raw.summary.avg_cost_per_call_usd,
      avgCostPerCallBrl: raw.summary.avg_cost_per_call_brl,
      callsWithDuration: raw.summary.calls_with_duration,
      totalDurationSeconds: raw.summary.total_duration_seconds,
      avgDurationSeconds: raw.summary.avg_duration_seconds,
    },
    series: raw.series.map((point) => ({
      timestamp: point.timestamp,
      calls: point.calls,
      costUsd: point.cost_usd,
      costBrl: point.cost_brl,
      durationSeconds: point.duration_seconds,
      provisionalCalls: point.provisional_calls,
    })),
    fx: {
      source: raw.fx.source,
      complete: raw.fx.complete,
      provisionalCalls: raw.fx.provisional_calls,
      missingRateCalls: raw.fx.missing_rate_calls,
      lastRateDate: raw.fx.last_rate_date,
    },
    reconciliation: {
      operationalCalls: raw.reconciliation.operational_calls,
      linkedOperationalCalls: raw.reconciliation.linked_operational_calls,
      linkageCoveragePct: raw.reconciliation.linkage_coverage_pct,
      componentAdjustmentCalls: raw.reconciliation.component_adjustment_calls,
    },
    breakdown: raw.breakdown.map((item) => ({
      category: item.category,
      costUsd: item.cost_usd,
      sharePct: item.share_pct,
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
      lastError: raw.sync.last_error,
      consecutiveFailures: raw.sync.consecutive_failures,
      lastRunStats: raw.sync.last_run_stats
        ? {
            processed: raw.sync.last_run_stats.processed,
            created: raw.sync.last_run_stats.created,
            updated: raw.sync.last_run_stats.updated,
            missingCost: raw.sync.last_run_stats.missing_cost,
            unresolvedTenant: raw.sync.last_run_stats.unresolved_tenant,
            missingFx: raw.sync.last_run_stats.missing_fx,
            errors: raw.sync.last_run_stats.errors,
          }
        : null,
    },
    summary: {
      totalCalls: raw.summary.total_calls,
      failedCalls: raw.summary.failed_calls,
      handoffCalls: raw.summary.handoff_calls,
      technicalFailureEvents: raw.summary.technical_failure_events,
      technicalFailureRatePct: raw.summary.technical_failure_rate_pct,
      repeatedBusinessErrors: raw.summary.repeated_business_errors,
      idempotencyHits: raw.summary.idempotency_hits,
    },
    searchFunnel: {
      attemptedCalls: raw.search_funnel.attempted_calls,
      blockedCalls: raw.search_funnel.blocked_calls,
      upstreamStartedCalls: raw.search_funnel.upstream_started_calls,
      completedCalls: raw.search_funnel.completed_calls,
      providerResultCalls: raw.search_funnel.provider_result_calls,
      reusedResultCalls: raw.search_funnel.reused_result_calls,
    },
    slotBlocks: {
      cpf: raw.slot_blocks.cpf,
      city: raw.slot_blocks.city,
      specialty: raw.slot_blocks.specialty,
      waitingForNewTurn: raw.slot_blocks.waiting_for_new_turn,
    },
    upstreamFailures: {
      auth: raw.upstream_failures.auth,
      timeout: raw.upstream_failures.timeout,
      network: raw.upstream_failures.network,
      fiveXx: raw.upstream_failures.five_xx,
      unexpected: raw.upstream_failures.unexpected,
    },
    handoffFlow: {
      recommendations: raw.handoff_flow.recommendations,
      nativeTransfers: raw.handoff_flow.native_transfers,
    },
    series: {
      failedCalls: raw.series.failed_calls.map((point) => ({
        timestamp: point.timestamp,
        value: point.value || 0,
      })),
      technicalFailureEvents: raw.series.technical_failure_events.map((point) => ({
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
      blocks: raw.series.blocks.map((point) => ({
        timestamp: point.timestamp,
        value: point.value || 0,
      })),
      successes: raw.series.successes.map((point) => ({
        timestamp: point.timestamp,
        value: point.value || 0,
      })),
      externalFailures: raw.series.external_failures.map((point) => ({
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
      technicalFailureEvents: raw.totals.technical_failure_events,
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
      updated: raw.result.updated || 0,
      missingCost: raw.result.missing_cost || 0,
      unresolvedTenant: raw.result.unresolved_tenant || 0,
      missingFx: raw.result.missing_fx || 0,
      errors: raw.result.errors || 0,
      locked: raw.result.locked,
    },
  }
}
