import type { AuditFilters, DashboardFilters } from "@/types/dashboard"

import { mapAuditEvents, mapAuditSummary } from "./adapters"
import { apiRequest } from "./client"
import { dashboardParams, normalizeAuditFilters, WINDOW_TO_MINUTES } from "./filters"
import { auditRecentSchema, auditSummarySchema } from "./schemas"

export async function fetchAuditSummary(filters: DashboardFilters) {
  const payload = await apiRequest("/ops/audit/summary", {
    params: {
      ...dashboardParams(filters),
      since_minutes: WINDOW_TO_MINUTES[filters.window],
    },
    schema: auditSummarySchema,
  })
  return mapAuditSummary(payload)
}

export async function fetchAuditRecent(filters: DashboardFilters, auditFilters: AuditFilters) {
  const normalizedAudit = normalizeAuditFilters(auditFilters)
  const payload = await apiRequest("/ops/audit/recent", {
    params: {
      ...dashboardParams(filters),
      limit: normalizedAudit.limit,
      tool_name: normalizedAudit.toolName,
      event_type: normalizedAudit.eventType,
      ok: normalizedAudit.ok,
    },
    schema: auditRecentSchema,
  })
  return mapAuditEvents(payload)
}
