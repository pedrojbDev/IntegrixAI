import { CheckCircle2, ListFilter, PhoneCall, XCircle } from "lucide-react"
import { useCallback } from "react"

import { EmptyState, ErrorState, PanelSkeleton } from "@/components/feedback/state-panels"
import { SectionHeader } from "@/components/layout/section-header"
import { StatCard } from "@/components/metrics/stat-card"
import { AuditEventsTable } from "@/components/tables/audit-events-table"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { useDashboardPreferences } from "@/features/shared-dashboard/dashboard-preferences"
import { useAuditQueries } from "@/hooks/use-dashboard-queries"
import { useRefreshEvent } from "@/hooks/use-refresh-event"
import { formatNumberBR } from "@/lib/format"

export function AuditPage() {
  const { filters, auditFilters, setAuditFilters } = useDashboardPreferences()
  const queries = useAuditQueries(filters, auditFilters)
  const loading = queries.summary.isLoading || queries.recent.isLoading
  const error = queries.summary.error || queries.recent.error || queries.health.error

  const refresh = useCallback(() => {
    void queries.health.refetch()
    void queries.summary.refetch()
    void queries.recent.refetch()
  }, [queries.health, queries.recent, queries.summary])
  useRefreshEvent(refresh)

  if (loading) {
    return <PanelSkeleton rows={9} />
  }

  if (error) {
    return <ErrorState error={error} />
  }

  const summary = queries.summary.data
  const events = queries.recent.data || []

  if (!summary) {
    return <EmptyState description="A API não retornou resumo de auditoria para os filtros atuais." title="Sem auditoria" />
  }

  return (
    <div className="space-y-4">
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={PhoneCall} label="Total" value={formatNumberBR(summary.totals.totalCalls)} />
        <StatCard icon={CheckCircle2} label="Sucesso" tone="success" value={formatNumberBR(summary.totals.successCalls)} />
        <StatCard icon={XCircle} label="Falha técnica" tone={summary.totals.technicalFailureEvents > 0 ? "danger" : "default"} value={formatNumberBR(summary.totals.technicalFailureEvents)} />
        <StatCard icon={ListFilter} label="Handoff" value={formatNumberBR(summary.totals.handoffCalls)} />
      </section>

      <Card>
        <CardHeader>
          <SectionHeader description="Filtros aplicados somente na trilha recente de eventos." title="Filtros de auditoria" />
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <label className="space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">Limite</span>
            <Select
              value={String(auditFilters.limit)}
              onChange={(event) => setAuditFilters({ ...auditFilters, limit: Number(event.target.value) })}
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </Select>
          </label>
          <label className="space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">Tool</span>
            <Input
              placeholder="tool_name"
              value={auditFilters.toolName || ""}
              onChange={(event) => setAuditFilters({ ...auditFilters, toolName: event.target.value })}
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">Evento</span>
            <Input
              placeholder="event_type"
              value={auditFilters.eventType || ""}
              onChange={(event) => setAuditFilters({ ...auditFilters, eventType: event.target.value })}
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">OK</span>
            <Select
              value={auditFilters.ok || "all"}
              onChange={(event) =>
                setAuditFilters({
                  ...auditFilters,
                  ok: event.target.value === "all" ? undefined : (event.target.value as "true" | "false"),
                })
              }
            >
              <option value="all">Todos</option>
              <option value="true">Somente OK</option>
              <option value="false">Somente resposta não OK</option>
            </Select>
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionHeader description="Eventos recentes sem exibir payload por padrão." title="Eventos recentes" />
        </CardHeader>
        <CardContent>
          {events.length ? (
            <AuditEventsTable items={events} />
          ) : (
            <EmptyState description="Nenhum evento encontrado para os filtros atuais." title="Sem eventos" />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
