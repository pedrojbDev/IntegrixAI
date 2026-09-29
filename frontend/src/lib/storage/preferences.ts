import { z } from "zod"

import type { AuditFilters, DashboardFilters } from "@/types/dashboard"

const STORAGE_KEY = "ops-dashboard:prefs:v1"

const preferencesSchema = z.object({
  filters: z
    .object({
      window: z.enum(["15m", "1h", "24h", "7d", "30d", "60d", "90d", "custom"]).catch("24h"),
      startDate: z.string().optional(),
      endDate: z.string().optional(),
      tenantId: z.string().optional(),
      assistantId: z.string().optional(),
    })
    .catch({ window: "24h" }),
  auditFilters: z
    .object({
      limit: z.coerce.number().catch(50),
      toolName: z.string().optional(),
      eventType: z.string().optional(),
      ok: z.enum(["true", "false"]).optional(),
    })
    .catch({ limit: 50 }),
  lastRoute: z.string().catch("/"),
})

export type DashboardPreferences = {
  filters: DashboardFilters
  auditFilters: AuditFilters
  lastRoute: string
}

export const defaultPreferences: DashboardPreferences = {
  filters: { window: "24h" },
  auditFilters: { limit: 50 },
  lastRoute: "/",
}

export function loadPreferences(): DashboardPreferences {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return defaultPreferences
    }
    const parsed = preferencesSchema.parse(JSON.parse(raw))
    const validCustom = parsed.filters.startDate && parsed.filters.endDate
    return {
      filters: {
        window: parsed.filters.window === "custom" && !validCustom ? "24h" : parsed.filters.window,
        startDate: validCustom ? parsed.filters.startDate : undefined,
        endDate: validCustom ? parsed.filters.endDate : undefined,
        tenantId: parsed.filters.tenantId,
        assistantId: parsed.filters.assistantId,
      },
      auditFilters: {
        limit: parsed.auditFilters.limit || 50,
        toolName: parsed.auditFilters.toolName,
        eventType: parsed.auditFilters.eventType,
        ok: parsed.auditFilters.ok,
      },
      lastRoute: parsed.lastRoute || "/",
    }
  } catch {
    return defaultPreferences
  }
}

export function savePreferences(preferences: DashboardPreferences) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
}

export function clearPreferences() {
  window.localStorage.removeItem(STORAGE_KEY)
}
