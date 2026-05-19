import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { fetchAuditRecent, fetchAuditSummary } from "@/lib/api/audit"
import { syncCosts } from "@/lib/api/costs"
import { fetchCosts, fetchHealth, fetchOverview, fetchResilience, fetchTools } from "@/lib/api/dashboard"
import { normalizeAuditFilters, normalizeDashboardFilters } from "@/lib/api/filters"
import type { AuditFilters, DashboardFilters } from "@/types/dashboard"

export function useHealthQuery(filters: DashboardFilters) {
  const normalized = normalizeDashboardFilters(filters)
  return useQuery({
    queryKey: ["health", normalized],
    queryFn: () => fetchHealth(normalized),
  })
}

export function useOverviewQueries(filters: DashboardFilters) {
  const normalized = normalizeDashboardFilters(filters)
  const health = useHealthQuery(normalized)
  const overview = useQuery({
    queryKey: ["overview", normalized],
    queryFn: () => fetchOverview(normalized),
  })
  const costs = useQuery({
    queryKey: ["costs", normalized],
    queryFn: () => fetchCosts(normalized),
  })
  const tools = useQuery({
    queryKey: ["tools", normalized],
    queryFn: () => fetchTools(normalized),
  })
  return { health, overview, costs, tools }
}

export function useDiagnosticsQueries(filters: DashboardFilters) {
  const normalized = normalizeDashboardFilters(filters)
  const health = useHealthQuery(normalized)
  const resilience = useQuery({
    queryKey: ["resilience", normalized],
    queryFn: () => fetchResilience(normalized),
  })
  return { health, resilience }
}

export function useAuditQueries(filters: DashboardFilters, auditFilters: AuditFilters) {
  const normalized = normalizeDashboardFilters(filters)
  const normalizedAudit = normalizeAuditFilters(auditFilters)
  const health = useHealthQuery(normalized)
  const summary = useQuery({
    queryKey: ["audit-summary", normalized],
    queryFn: () => fetchAuditSummary(normalized),
  })
  const recent = useQuery({
    queryKey: ["audit-recent", normalized, normalizedAudit],
    queryFn: () => fetchAuditRecent(normalized, normalizedAudit),
  })
  return { health, summary, recent }
}

export function useSyncCostsMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: syncCosts,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["health"] }),
        queryClient.invalidateQueries({ queryKey: ["overview"] }),
        queryClient.invalidateQueries({ queryKey: ["costs"] }),
        queryClient.invalidateQueries({ queryKey: ["tools"] }),
        queryClient.invalidateQueries({ queryKey: ["resilience"] }),
        queryClient.invalidateQueries({ queryKey: ["audit-summary"] }),
      ])
    },
  })
}
