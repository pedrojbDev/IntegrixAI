import type { DashboardFilters } from "@/types/dashboard"

import { mapCosts, mapHealth, mapOverview, mapResilience, mapTool } from "./adapters"
import { apiRequest } from "./client"
import { dashboardParams } from "./filters"
import { costsSchema, healthSchema, overviewSchema, resilienceSchema, toolsSchema } from "./schemas"

export async function fetchHealth(filters: DashboardFilters) {
  const payload = await apiRequest("/ops/dashboard/health", {
    params: dashboardParams(filters),
    schema: healthSchema,
  })
  return mapHealth(payload)
}

export async function fetchOverview(filters: DashboardFilters) {
  const payload = await apiRequest("/ops/dashboard/overview", {
    params: dashboardParams(filters),
    schema: overviewSchema,
  })
  return mapOverview(payload)
}

export async function fetchCosts(filters: DashboardFilters) {
  const payload = await apiRequest("/ops/dashboard/costs", {
    params: dashboardParams(filters),
    schema: costsSchema,
  })
  return mapCosts(payload)
}

export async function fetchTools(filters: DashboardFilters) {
  const payload = await apiRequest("/ops/dashboard/tools", {
    params: dashboardParams(filters),
    schema: toolsSchema,
  })
  return payload.items.map(mapTool)
}

export async function fetchResilience(filters: DashboardFilters) {
  const payload = await apiRequest("/ops/dashboard/resilience", {
    params: dashboardParams(filters),
    schema: resilienceSchema,
  })
  return mapResilience(payload)
}
