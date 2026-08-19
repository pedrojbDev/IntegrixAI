import type { DashboardFilters, ReportPeriodDays } from "@/types/dashboard"

import { downloadFile } from "./client"
import { normalizeDashboardFilters } from "./filters"

export const REPORT_PERIOD_OPTIONS: Array<{ value: ReportPeriodDays; label: string }> = [
  { value: 7, label: "7 dias" },
  { value: 15, label: "15 dias" },
  { value: 30, label: "30 dias" },
  { value: 90, label: "90 dias" },
]

export async function downloadOperationalReport(filters: DashboardFilters, periodDays: ReportPeriodDays) {
  const normalized = normalizeDashboardFilters(filters)
  await downloadFile(
    "/ops/reports/operational.pdf",
    {
      period_days: periodDays,
      tenant_id: normalized.tenantId,
      assistant_id: normalized.assistantId,
    },
    `relatorio-operacional-${periodDays}-dias.pdf`,
  )
}
