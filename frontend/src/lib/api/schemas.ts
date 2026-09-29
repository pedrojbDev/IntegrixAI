import { z } from "zod"

export const sessionResponseSchema = z.object({
  authenticated: z.literal(true),
  principal: z.object({
    id: z.string(),
    email: z.string(),
    role: z.enum(["platform_admin", "tenant_user"]),
    tenant_ids: z.array(z.string()),
    must_change_password: z.boolean(),
  }),
}).strict()

export const loginRequestSchema = z.object({
  email: z.string().email("Informe um email válido."),
  password: z.string().min(8, "A senha deve ter pelo menos 8 caracteres."),
}).strict()

const numeric = z.coerce.number().catch(0)
const nullableNumeric = z.coerce.number().nullable().catch(null)
const nullableString = z.string().nullable().catch(null)

export const toolPerformanceSchema = z
  .object({
    tool_name: z.string().catch("unknown"),
    total_calls: numeric,
    success_calls: numeric,
    failed_calls: numeric,
    handoff_calls: numeric,
    avg_duration_ms: numeric,
    failure_rate_pct: numeric,
    technical_failure_events: numeric,
    technical_failure_rate_pct: numeric,
    unique_calls: numeric,
  })
  .passthrough()

export const healthSchema = z
  .object({
    window: z.enum(["15m", "1h", "24h", "7d", "30d", "60d", "90d", "custom"]).catch("24h"),
    health_state: z.string().catch("no_data"),
    sync: z
      .object({
        last_synced_at: nullableString,
        freshness_seconds: z.number().nullable().catch(null),
        freshness_state: z.string().catch("unknown"),
        last_error: nullableString,
        consecutive_failures: numeric,
        last_run_stats: z
          .object({
            processed: numeric,
            created: numeric,
            updated: numeric,
            missing_cost: numeric,
            unresolved_tenant: numeric,
            missing_fx: numeric,
            errors: numeric,
          })
          .nullable()
          .catch(null),
      })
      .catch({
        last_synced_at: null,
        freshness_seconds: null,
        freshness_state: "unknown",
        last_error: null,
        consecutive_failures: 0,
        last_run_stats: null,
      }),
    counters: z
      .object({
        total_calls: numeric,
        vapi_calls: numeric,
        failed_calls: numeric,
        handoff_calls: numeric,
        technical_failure_events: numeric,
        technical_failure_rate_pct: numeric,
        tool_execution_count: numeric,
        calls_with_cost: numeric,
        calls_without_cost: numeric,
        repeated_business_errors: numeric,
        idempotency_hits: numeric,
        coverage_pct: numeric,
      })
      .catch({
        total_calls: 0,
        vapi_calls: 0,
        failed_calls: 0,
        handoff_calls: 0,
        technical_failure_events: 0,
        technical_failure_rate_pct: 0,
        tool_execution_count: 0,
        calls_with_cost: 0,
        calls_without_cost: 0,
        repeated_business_errors: 0,
        idempotency_hits: 0,
        coverage_pct: 0,
      }),
    top_degrading_tools: z.array(toolPerformanceSchema).catch([]),
  })
  .passthrough()

export const overviewSchema = z
  .object({
    window: z.enum(["15m", "1h", "24h", "7d", "30d", "60d", "90d", "custom"]).catch("24h"),
    since: nullableString,
    kpis: z
      .object({
        total_calls: numeric,
        success_calls: numeric,
        failed_calls: numeric,
        handoff_calls: numeric,
        avg_duration_ms: numeric,
        automated_resolution_calls: numeric,
        successful_handoff_calls: numeric,
        normal_completion_calls: numeric,
        successful_agent_calls: numeric,
        agent_success_rate_pct: numeric,
        unresolved_calls: numeric,
        technical_failure_events: numeric,
        tool_execution_count: numeric,
        technical_failure_rate_pct: numeric,
      })
      .catch({
        total_calls: 0,
        success_calls: 0,
        failed_calls: 0,
        handoff_calls: 0,
        avg_duration_ms: 0,
        automated_resolution_calls: 0,
        successful_handoff_calls: 0,
        normal_completion_calls: 0,
        successful_agent_calls: 0,
        agent_success_rate_pct: 0,
        unresolved_calls: 0,
        technical_failure_events: 0,
        tool_execution_count: 0,
        technical_failure_rate_pct: 0,
      }),
    series: z
      .array(
        z.object({
          timestamp: z.string(),
          calls: numeric,
          handoffs: numeric,
          successful_handoffs: numeric,
          automated_resolutions: numeric,
          normal_completions: numeric,
          unresolved_calls: numeric,
        }),
      )
      .catch([]),
  })
  .passthrough()

export const costsSchema = z
  .object({
    visibility: z.enum(["enabled", "admin_preview", "hidden"]).catch("hidden"),
    summary: z
      .object({
        total_cost_usd: numeric,
        total_cost_brl: nullableNumeric,
        vapi_calls: numeric,
        calls_with_cost: numeric,
        calls_without_cost: numeric,
        coverage_pct: numeric,
        avg_cost_per_call_usd: numeric,
        avg_cost_per_call_brl: nullableNumeric,
        calls_with_duration: numeric,
        total_duration_seconds: numeric,
        avg_duration_seconds: numeric,
      })
      .catch({
        total_cost_usd: 0,
        total_cost_brl: null,
        vapi_calls: 0,
        calls_with_cost: 0,
        calls_without_cost: 0,
        coverage_pct: 0,
        avg_cost_per_call_usd: 0,
        avg_cost_per_call_brl: null,
        calls_with_duration: 0,
        total_duration_seconds: 0,
        avg_duration_seconds: 0,
      }),
    series: z
      .array(
        z.object({
          timestamp: z.string(),
          calls: numeric,
          cost_usd: numeric,
          cost_brl: nullableNumeric,
          duration_seconds: numeric,
          provisional_calls: numeric,
        }),
      )
      .catch([]),
    fx: z
      .object({
        source: z.string().catch("BCB_PTAX"),
        basis: z.string().catch("closing_sale_rate_on_call_date"),
        complete: z.boolean().catch(false),
        provisional_calls: numeric,
        missing_rate_calls: numeric,
        last_rate_date: nullableString,
      })
      .catch({
        source: "BCB_PTAX",
        basis: "closing_sale_rate_on_call_date",
        complete: false,
        provisional_calls: 0,
        missing_rate_calls: 0,
        last_rate_date: null,
      }),
    reconciliation: z
      .object({
        operational_calls: numeric,
        linked_operational_calls: numeric,
        linkage_coverage_pct: numeric,
        component_adjustment_calls: numeric,
      })
      .catch({
        operational_calls: 0,
        linked_operational_calls: 0,
        linkage_coverage_pct: 0,
        component_adjustment_calls: 0,
      }),
    breakdown: z
      .array(
        z.object({
          category: z.string(),
          cost_usd: numeric,
          share_pct: numeric,
        }),
      )
      .catch([]),
  })
  .passthrough()

export const toolsSchema = z
  .object({
    items: z.array(toolPerformanceSchema).catch([]),
  })
  .passthrough()

export const resilienceSchema = z
  .object({
    health_state: z.string().catch("no_data"),
    sync: healthSchema.shape.sync,
    summary: z
      .object({
        total_calls: numeric,
        failed_calls: numeric,
        handoff_calls: numeric,
        technical_failure_events: numeric,
        technical_failure_rate_pct: numeric,
        repeated_business_errors: numeric,
        idempotency_hits: numeric,
      })
      .catch({
        total_calls: 0,
        failed_calls: 0,
        handoff_calls: 0,
        technical_failure_events: 0,
        technical_failure_rate_pct: 0,
        repeated_business_errors: 0,
        idempotency_hits: 0,
      }),
    search_funnel: z
      .object({
        attempted_calls: numeric,
        blocked_calls: numeric,
        upstream_started_calls: numeric,
        completed_calls: numeric,
        provider_result_calls: numeric,
        reused_result_calls: numeric,
      })
      .catch({
        attempted_calls: 0,
        blocked_calls: 0,
        upstream_started_calls: 0,
        completed_calls: 0,
        provider_result_calls: 0,
        reused_result_calls: 0,
      }),
    slot_blocks: z
      .object({ cpf: numeric, city: numeric, specialty: numeric, waiting_for_new_turn: numeric })
      .catch({ cpf: 0, city: 0, specialty: 0, waiting_for_new_turn: 0 }),
    upstream_failures: z
      .object({ auth: numeric, timeout: numeric, network: numeric, five_xx: numeric, unexpected: numeric })
      .catch({ auth: 0, timeout: 0, network: 0, five_xx: 0, unexpected: 0 }),
    handoff_flow: z
      .object({ recommendations: numeric, native_transfers: numeric })
      .catch({ recommendations: 0, native_transfers: 0 }),
    voice_quality: z
      .object({
        calls_with_metrics: numeric,
        average_turn_latency_ms: nullableNumeric,
        total_assistant_interruptions: numeric,
        calls_with_assistant_interruptions: numeric,
      })
      .catch({
        calls_with_metrics: 0,
        average_turn_latency_ms: null,
        total_assistant_interruptions: 0,
        calls_with_assistant_interruptions: 0,
      }),
    series: z
      .object({
        failed_calls: z.array(z.object({ timestamp: z.string(), value: numeric })).catch([]),
        technical_failure_events: z.array(z.object({ timestamp: z.string(), value: numeric })).catch([]),
        idempotency_hits: z.array(z.object({ timestamp: z.string(), value: numeric })).catch([]),
        repeated_business_errors: z.array(z.object({ timestamp: z.string(), value: numeric })).catch([]),
        blocks: z.array(z.object({ timestamp: z.string(), value: numeric })).catch([]),
        successes: z.array(z.object({ timestamp: z.string(), value: numeric })).catch([]),
        external_failures: z.array(z.object({ timestamp: z.string(), value: numeric })).catch([]),
        turn_latency_average_ms: z.array(z.object({ timestamp: z.string(), value: numeric })).catch([]),
        assistant_interruptions: z.array(z.object({ timestamp: z.string(), value: numeric })).catch([]),
      })
      .catch({
        failed_calls: [],
        technical_failure_events: [],
        idempotency_hits: [],
        repeated_business_errors: [],
        blocks: [],
        successes: [],
        external_failures: [],
        turn_latency_average_ms: [],
        assistant_interruptions: [],
      }),
    top_failure_tools: z.array(toolPerformanceSchema).catch([]),
    top_handoff_tools: z.array(toolPerformanceSchema).catch([]),
    business_error_tools: z
      .array(
        z.object({
          tool_name: z.string().catch("unknown"),
          retries: numeric,
          scopes: numeric,
        }),
      )
      .catch([]),
  })
  .passthrough()

export const auditSummarySchema = z
  .object({
    totals: z
      .object({
        total_calls: numeric,
        success_calls: numeric,
        failed_calls: numeric,
        handoff_calls: numeric,
        technical_failure_events: numeric,
        avg_duration_ms: numeric,
      })
      .catch({
        total_calls: 0,
        success_calls: 0,
        failed_calls: 0,
        handoff_calls: 0,
        technical_failure_events: 0,
        avg_duration_ms: 0,
      }),
  })
  .passthrough()

export const auditRecentSchema = z
  .object({
    items: z
      .array(
        z
          .object({
            id: z.union([z.string(), z.number()]).catch(""),
            tenant_id: z.string().nullable().catch(null),
            call_id: z.string().nullable().catch(null),
            tool_name: z.string().nullable().catch(null),
            event_type: z.string().nullable().catch(null),
            final_state: z.string().nullable().catch(null),
            ok: z.boolean().nullable().catch(null),
            duration_ms: numeric,
            error_code: z.string().nullable().catch(null),
            created_at: z.string().catch(""),
          })
          .passthrough(),
      )
      .catch([]),
  })
  .passthrough()

export const costSyncSchema = z
  .object({
    ok: z.boolean(),
    result: z.object({
      processed: numeric,
      created: numeric,
      updated: numeric,
      missing_cost: numeric,
      unresolved_tenant: numeric,
      missing_fx: numeric,
      errors: numeric,
      locked: z.boolean().catch(false),
    }),
  })
  .passthrough()

export const opsUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  role: z.enum(["platform_admin", "tenant_user"]),
  tenant_ids: z.array(z.string()),
  is_active: z.boolean(),
  must_change_password: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
})

export const opsUsersSchema = z.array(opsUserSchema)

export const temporaryPasswordSchema = z.object({
  temporary_password: z.string(),
}).passthrough()

export const createdUserSchema = z.object({
  user: opsUserSchema,
  temporary_password: z.string(),
})
