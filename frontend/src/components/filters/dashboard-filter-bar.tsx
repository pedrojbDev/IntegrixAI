import { FileDown, RefreshCw, Search, Zap } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { WINDOW_OPTIONS } from "@/lib/api/filters"
import { REPORT_PERIOD_OPTIONS } from "@/lib/api/reports"
import type { DashboardFilters, ReportPeriodDays } from "@/types/dashboard"

type DashboardFilterBarProps = {
  filters: DashboardFilters
  onChange: (filters: DashboardFilters) => void
  onRefresh: () => void
  onSync: () => void
  onExportReport: (periodDays: ReportPeriodDays) => void
  refreshing?: boolean
  syncing?: boolean
  exporting?: boolean
  isAdmin: boolean
  allowedTenants: string[]
}

export function DashboardFilterBar({
  filters,
  onChange,
  onRefresh,
  onSync,
  onExportReport,
  refreshing,
  syncing,
  exporting,
  isAdmin,
  allowedTenants,
}: DashboardFilterBarProps) {
  const [reportPeriodDays, setReportPeriodDays] = useState<ReportPeriodDays>(30)
  const [startDate, setStartDate] = useState(filters.startDate || "")
  const [endDate, setEndDate] = useState(filters.endDate || "")
  const [dateError, setDateError] = useState("")

  function applyDates() {
    const days = (Date.parse(`${endDate}T00:00:00Z`) - Date.parse(`${startDate}T00:00:00Z`)) / 86400000
    if (!startDate || !endDate || !Number.isFinite(days) || days < 0 || days > 365) {
      setDateError("Escolha duas datas em ordem, com até 366 dias no intervalo.")
      return
    }
    setDateError("")
    onChange({ ...filters, window: "custom", startDate, endDate })
  }

  function changeWindow(window: DashboardFilters["window"]) {
    setDateError("")
    if (window === "custom") {
      const today = new Intl.DateTimeFormat("sv-SE", { timeZone: "America/Sao_Paulo" }).format(new Date())
      const start = filters.startDate || today
      const end = filters.endDate || today
      setStartDate(start)
      setEndDate(end)
      onChange({ ...filters, window, startDate: start, endDate: end })
    } else {
      onChange({ ...filters, window, startDate: undefined, endDate: undefined })
    }
  }

  return (
    <div className="flex flex-col gap-3 border-b border-border bg-background/95 px-4 py-3 backdrop-blur lg:px-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
        <div className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">Janela</span>
            <Select value={filters.window} onChange={(event) => changeWindow(event.target.value as DashboardFilters["window"])}>
              {WINDOW_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </label>
          <label className="space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">Tenant</span>
            {isAdmin ? (
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
                <Input
                  className="pl-9"
                  placeholder="tenant_id ou visão global autorizada"
                  value={filters.tenantId || ""}
                  onChange={(event) => onChange({ ...filters, tenantId: event.target.value })}
                />
              </div>
            ) : (
              <Select
                value={filters.tenantId || ""}
                onChange={(event) => onChange({ ...filters, tenantId: event.target.value })}
              >
                {allowedTenants.map((tenantId) => (
                  <option key={tenantId} value={tenantId}>{tenantId}</option>
                ))}
              </Select>
            )}
          </label>
          <label className="space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">Assistant</span>
            <Input
              placeholder="assistant_id"
              value={filters.assistantId || ""}
              onChange={(event) => onChange({ ...filters, assistantId: event.target.value })}
            />
          </label>
        </div>
        <div className="flex gap-2">
          <Button className="flex-1 lg:flex-none" disabled={refreshing} onClick={onRefresh} type="button" variant="outline">
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Atualizar
          </Button>
          {isAdmin ? (
            <Button className="flex-1 lg:flex-none" disabled={syncing} onClick={onSync} type="button">
              <Zap className="h-4 w-4" aria-hidden="true" />
              Sync custos
            </Button>
          ) : null}
        </div>
        <div className="flex items-end gap-2 border-t border-border pt-3 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
          <label className="min-w-28 space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">Relatório PDF</span>
            <Select value={String(reportPeriodDays)} onChange={(event) => setReportPeriodDays(Number(event.target.value) as ReportPeriodDays)}>
              {REPORT_PERIOD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </label>
          <Button disabled={exporting} onClick={() => onExportReport(reportPeriodDays)} type="button" variant="outline">
            <FileDown className="h-4 w-4" aria-hidden="true" />
            {exporting ? "Gerando..." : "Exportar"}
          </Button>
        </div>
      </div>
      {filters.window === "custom" ? (
        <div className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-muted/30 p-3" role="group" aria-label="Intervalo personalizado">
          <label className="space-y-1.5">
            <span className="block text-xs font-medium text-muted-foreground">De</span>
            <Input aria-label="Data inicial" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          </label>
          <label className="space-y-1.5">
            <span className="block text-xs font-medium text-muted-foreground">Até</span>
            <Input aria-label="Data final" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </label>
          <Button onClick={applyDates} type="button" variant="outline">Aplicar datas</Button>
          <span className="text-xs text-muted-foreground">Datas inclusivas · horário de São Paulo · até 366 dias</span>
          {dateError ? <p className="w-full text-sm text-destructive" role="alert">{dateError}</p> : null}
        </div>
      ) : null}
    </div>
  )
}
