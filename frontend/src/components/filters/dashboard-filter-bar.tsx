import { RefreshCw, Search, Zap } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { WINDOW_OPTIONS } from "@/lib/api/filters"
import type { DashboardFilters } from "@/types/dashboard"

type DashboardFilterBarProps = {
  filters: DashboardFilters
  onChange: (filters: DashboardFilters) => void
  onRefresh: () => void
  onSync: () => void
  refreshing?: boolean
  syncing?: boolean
}

export function DashboardFilterBar({
  filters,
  onChange,
  onRefresh,
  onSync,
  refreshing,
  syncing,
}: DashboardFilterBarProps) {
  return (
    <div className="flex flex-col gap-3 border-b border-border bg-background/95 px-4 py-3 backdrop-blur lg:flex-row lg:items-center lg:px-6">
      <div className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">Janela</span>
          <Select value={filters.window} onChange={(event) => onChange({ ...filters, window: event.target.value as DashboardFilters["window"] })}>
            {WINDOW_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">Tenant</span>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <Input
              className="pl-9"
              placeholder="tenant_id"
              value={filters.tenantId || ""}
              onChange={(event) => onChange({ ...filters, tenantId: event.target.value })}
            />
          </div>
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
        <Button className="flex-1 lg:flex-none" disabled={syncing} onClick={onSync} type="button">
          <Zap className="h-4 w-4" aria-hidden="true" />
          Sync custos
        </Button>
      </div>
    </div>
  )
}
