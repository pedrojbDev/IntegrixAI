import { AlertTriangle, GitPullRequest, Repeat, ShieldCheck } from "lucide-react"
import { useCallback } from "react"

import { ResponsiveLineChart } from "@/components/charts/responsive-line-chart"
import { EmptyState, ErrorState, PanelSkeleton } from "@/components/feedback/state-panels"
import { SectionHeader } from "@/components/layout/section-header"
import { StatCard } from "@/components/metrics/stat-card"
import { ToolsTable } from "@/components/tables/tools-table"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { useDashboardPreferences } from "@/features/shared-dashboard/dashboard-preferences"
import { useDiagnosticsQueries } from "@/hooks/use-dashboard-queries"
import { useRefreshEvent } from "@/hooks/use-refresh-event"
import { formatNumberBR, formatPercent } from "@/lib/format"

function healthLabel(value: string) {
  if (value === "stable") return "Estável"
  if (value === "critical") return "Crítico"
  if (value === "warning") return "Atenção"
  return "Sem dados"
}

function syncLabel(value: string) {
  if (value === "fresh") return "Atual"
  if (value === "delayed") return "Com atraso"
  if (value === "stale") return "Atrasado"
  return "Desconhecido"
}

export function DiagnosticsPage() {
  const { filters } = useDashboardPreferences()
  const queries = useDiagnosticsQueries(filters)
  const loading = queries.health.isLoading || queries.resilience.isLoading
  const error = queries.health.error || queries.resilience.error

  const refresh = useCallback(() => {
    void queries.health.refetch()
    void queries.resilience.refetch()
  }, [queries.health, queries.resilience])
  useRefreshEvent(refresh)

  if (loading) {
    return <PanelSkeleton rows={9} />
  }

  if (error) {
    return <ErrorState error={error} />
  }

  const health = queries.health.data
  const resilience = queries.resilience.data

  if (!health || !resilience) {
    return <EmptyState description="A API não retornou sinais de diagnóstico para a janela atual." title="Sem diagnóstico" />
  }

  return (
    <div className="space-y-4">
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={ShieldCheck} label="Saúde" tone={health.healthState === "critical" ? "danger" : health.healthState === "warning" ? "warning" : "success"} value={healthLabel(health.healthState)} />
        <StatCard detail={syncLabel(health.sync.freshnessState)} icon={Repeat} label="Sync de custo" value={health.sync.freshnessSeconds == null ? "Sem histórico" : `${Math.round(health.sync.freshnessSeconds / 60)} min`} />
        <StatCard icon={GitPullRequest} label="Idempotency hits" value={formatNumberBR(resilience.summary.idempotencyHits)} />
        <StatCard icon={AlertTriangle} label="Erros repetidos" tone={resilience.summary.repeatedBusinessErrors > 0 ? "warning" : "default"} value={formatNumberBR(resilience.summary.repeatedBusinessErrors)} />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <SectionHeader description="Falhas registradas em tool calls por bucket." title="Falhas por período" />
          </CardHeader>
          <CardContent>
            {resilience.series.failedCalls.length ? (
              <ResponsiveLineChart
                data={resilience.series.failedCalls}
                series={[{ key: "value", label: "Falhas", color: "hsl(var(--destructive))", area: true }]}
              />
            ) : (
              <EmptyState description="Nenhum bucket com falha foi encontrado." title="Sem falhas na série" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <SectionHeader description="Reaproveitamentos e erros de negócio repetidos." title="Resiliência" />
          </CardHeader>
          <CardContent>
            <ResponsiveLineChart
              data={mergeResilienceSeries(resilience.series.idempotencyHits, resilience.series.repeatedBusinessErrors)}
              series={[
                { key: "idempotency", label: "Idempotência", color: "hsl(var(--primary))", area: true },
                { key: "businessErrors", label: "Erros repetidos", color: "hsl(var(--warning))" },
              ]}
            />
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader>
            <SectionHeader description="Cobertura financeira na janela." title="Cobertura" />
          </CardHeader>
          <CardContent>
            <p className="font-mono text-3xl font-semibold">{formatPercent(health.counters.coveragePct)}</p>
            <p className="mt-2 text-sm text-muted-foreground">
              {formatNumberBR(health.counters.callsWithCost)} de {formatNumberBR(health.counters.totalCalls)} calls com custo.
            </p>
          </CardContent>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader>
            <SectionHeader description="Distribuição de tentativas repetidas por ferramenta." title="Erros repetidos por tool" />
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            {resilience.businessErrorTools.length ? (
              resilience.businessErrorTools.map((item) => (
                <div className="rounded-md border border-border p-3" key={item.toolName}>
                  <p className="truncate text-sm font-medium">{item.toolName}</p>
                  <p className="mt-2 font-mono text-xl">{formatNumberBR(item.retries)}</p>
                  <p className="text-xs text-muted-foreground">{formatNumberBR(item.scopes)} escopos</p>
                </div>
              ))
            ) : (
              <EmptyState description="Nenhuma repetição de erro de negócio encontrada." title="Sem repetição" />
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <SectionHeader description="Tools ordenadas por taxa de falha." title="Piores falhas" />
          </CardHeader>
          <CardContent>
            {resilience.topFailureTools.length ? <ToolsTable items={resilience.topFailureTools} /> : <EmptyState description="Sem tools com falha na janela." title="Sem falhas" />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <SectionHeader description="Tools com maior volume de handoff." title="Maior handoff" />
          </CardHeader>
          <CardContent>
            {resilience.topHandoffTools.length ? <ToolsTable items={resilience.topHandoffTools} /> : <EmptyState description="Sem handoff registrado na janela." title="Sem handoff" />}
          </CardContent>
        </Card>
      </section>
    </div>
  )
}

function mergeResilienceSeries(
  idempotency: Array<{ timestamp: string; value: number }>,
  businessErrors: Array<{ timestamp: string; value: number }>,
) {
  const points = new Map<string, { timestamp: string; idempotency: number; businessErrors: number }>()
  for (const item of idempotency) {
    points.set(item.timestamp, { timestamp: item.timestamp, idempotency: item.value, businessErrors: 0 })
  }
  for (const item of businessErrors) {
    const existing = points.get(item.timestamp)
    points.set(item.timestamp, {
      timestamp: item.timestamp,
      idempotency: existing?.idempotency || 0,
      businessErrors: item.value,
    })
  }
  return [...points.values()].sort((left, right) => left.timestamp.localeCompare(right.timestamp))
}
