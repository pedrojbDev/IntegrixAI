import type { AuditFilters, DashboardFilters, WindowKey } from "@/types/dashboard"

export const WINDOW_OPTIONS: Array<{ value: WindowKey; label: string }> = [
  { value: "15m", label: "15 minutos" },
  { value: "1h", label: "1 hora" },
  { value: "24h", label: "24 horas" },
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "60d", label: "60 dias" },
  { value: "90d", label: "90 dias" },
]

export const WINDOW_TO_MINUTES: Record<WindowKey, number> = {
  "15m": 15,
  "1h": 60,
  "24h": 1440,
  "7d": 10080,
  "30d": 43200,
  "60d": 86400,
  "90d": 129600,
}

function clean(value: string | undefined) {
  const next = value?.trim()
  return next ? next : undefined
}

export function normalizeDashboardFilters(filters: DashboardFilters): DashboardFilters {
  return {
    window: filters.window || "24h",
    tenantId: clean(filters.tenantId),
    assistantId: clean(filters.assistantId),
  }
}

export function normalizeAuditFilters(filters: AuditFilters): AuditFilters {
  return {
    limit: Number(filters.limit || 50),
    toolName: clean(filters.toolName),
    eventType: clean(filters.eventType),
    ok: filters.ok,
  }
}

export function dashboardParams(filters: DashboardFilters) {
  const normalized = normalizeDashboardFilters(filters)
  return {
    window: normalized.window,
    tenant_id: normalized.tenantId,
    assistant_id: normalized.assistantId,
  }
}
