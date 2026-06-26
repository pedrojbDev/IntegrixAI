import { Activity, BadgeDollarSign, CheckCircle2, Clock3, PhoneForwarded } from "lucide-react"
import { useCallback } from "react"

import { ResponsiveLineChart } from "@/components/charts/responsive-line-chart"
import { EmptyState, ErrorState, PanelSkeleton } from "@/components/feedback/state-panels"
import { SectionHeader } from "@/components/layout/section-header"
import { StatCard } from "@/components/metrics/stat-card"
import { ToolsTable } from "@/components/tables/tools-table"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { useDashboardPreferences } from "@/features/shared-dashboard/dashboard-preferences"
import { useOverviewQueries } from "@/hooks/use-dashboard-queries"
import { useRefreshEvent } from "@/hooks/use-refresh-event"
import {
  formatCurrencyUSD,
  formatDurationMs,
  formatDurationSeconds,
  formatNumberBR,
  formatPercent,
} from "@/lib/format"

function rate(part: number, total: number) {
  return total > 0 ? (part / total) * 100 : 0
}

export function OverviewPage() {
  const { filters } = useDashboardPreferences()
  const queries = useOverviewQueries(filters)
  const loading = queries.overview.isLoading || queries.costs.isLoading || queries.tools.isLoading
  const error = queries.overview.error || queries.costs.error || queries.tools.error || queries.health.error

  const refresh = useCallback(() => {
    void queries.health.refetch()
    void queries.overview.refetch()
    void queries.costs.refetch()
    void queries.tools.refetch()
  }, [queries.costs, queries.health, queries.overview, queries.tools])
  useRefreshEvent(refresh)

  if (loading) {
    return <PanelSkeleton rows={10} />
  }

  if (error) {
    return <ErrorState error={error} />
  }

  const overview = queries.overview.data
  const costs = queries.costs.data
  const tools = queries.tools.data || []
  const health = queries.health.data

  if (!overview || !costs || !health) {
    return <EmptyState description="Nenhum dado operacional foi retornado para os filtros atuais." title="Sem dados" />
  }

  const totalCalls = overview.kpis.totalCalls
  const successRate = rate(overview.kpis.successCalls, totalCalls)
  const handoffRate = rate(overview.kpis.handoffCalls, totalCalls)
  const failureRate = rate(overview.kpis.failedCalls, totalCalls)
  const coverageRate = rate(costs.summary.callsWithCost, totalCalls)
  const costPerMinute = costs.summary.totalDurationSeconds > 0
    ? costs.summary.totalCostUsd / (costs.summary.totalDurationSeconds / 60)
    : 0
  return (
    <div className="space-y-4">
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard detail="Calls na janela atual" icon={Activity} label="Total de calls" value={formatNumberBR(totalCalls)} />
        <StatCard detail={`${formatNumberBR(overview.kpis.successCalls)} resolvidas`} icon={CheckCircle2} label="Resolução" tone="success" value={formatPercent(successRate)} />
        <StatCard detail={`${formatNumberBR(overview.kpis.handoffCalls)} transferências`} icon={PhoneForwarded} label="Handoff" tone={handoffRate >= 20 ? "warning" : "default"} value={formatPercent(handoffRate)} />
        <StatCard detail={`${formatNumberBR(costs.summary.callsWithCost)} calls com custo`} icon={BadgeDollarSign} label="Custo total" value={formatCurrencyUSD(costs.summary.totalCostUsd)} />
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard detail={`${formatNumberBR(overview.kpis.failedCalls)} falhas`} label="Falha" tone={failureRate >= 10 ? "danger" : "default"} value={formatPercent(failureRate)} />
        <StatCard detail="Calls com custo sincronizado" label="Cobertura de custo" tone={coverageRate < 80 && totalCalls > 0 ? "warning" : "default"} value={formatPercent(coverageRate)} />
        <StatCard detail="Base nas chamadas sincronizadas" label="Custo médio por call" value={formatCurrencyUSD(costs.summary.avgCostPerCallUsd)} />
        <StatCard
          detail={`${formatNumberBR(costs.summary.callsWithDuration)} calls com duração | total ${formatDurationSeconds(costs.summary.totalDurationSeconds)}`}
          icon={Clock3}
          label="Tempo médio de ligação"
          value={formatDurationSeconds(costs.summary.avgDurationSeconds)}
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <SectionHeader description="Volume de chamadas e transferências por bucket." title="Chamadas e handoff" />
          </CardHeader>
          <CardContent>
            {overview.series.length ? (
              <ResponsiveLineChart
                data={overview.series}
                series={[
                  { key: "calls", label: "Calls", color: "hsl(var(--primary))", area: true },
                  { key: "handoffs", label: "Handoff", color: "hsl(var(--warning))" },
                ]}
              />
            ) : (
              <EmptyState description="A janela selecionada ainda não possui buckets de chamada." title="Sem série temporal" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <SectionHeader description="Gasto agregado por bucket sincronizado." title="Custo por período" />
          </CardHeader>
          <CardContent>
            {costs.series.length ? (
              <ResponsiveLineChart
                data={costs.series.map((point) => ({ ...point, cost: point.costUsd }))}
                series={[{ key: "cost", label: "Custo", color: "hsl(var(--primary))", area: true }]}
              />
            ) : (
              <EmptyState description="Nenhum custo sincronizado para os filtros atuais." title="Sem custos" />
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader>
            <SectionHeader description="Sinais operacionais calculados a partir da janela." title="Resumo executivo" />
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-4">
            <div className="rounded-md border border-border p-3">
              <p className="text-xs text-muted-foreground">Saúde</p>
              <Badge className="mt-2" variant={health.healthState === "stable" ? "success" : health.healthState === "critical" ? "destructive" : "warning"}>
                {health.healthState === "stable" ? "Estável" : health.healthState === "critical" ? "Crítico" : health.healthState === "warning" ? "Atenção" : "Sem dados"}
              </Badge>
            </div>
            <div className="rounded-md border border-border p-3">
              <p className="text-xs text-muted-foreground">Sync</p>
              <p className="mt-2 text-sm font-medium">{health.sync.freshnessState}</p>
            </div>
            <div className="rounded-md border border-border p-3">
              <p className="text-xs text-muted-foreground">Custo/min</p>
              <p className="mt-2 truncate text-sm font-medium">{formatCurrencyUSD(costPerMinute)}</p>
            </div>
            <div className="rounded-md border border-border p-3">
              <p className="text-xs text-muted-foreground">Tempo médio tool</p>
              <p className="mt-2 truncate text-sm font-medium">{formatDurationMs(overview.kpis.avgDurationMs)}</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <SectionHeader description="Tools com maior peso operacional nesta janela." title="Destaques por tool" />
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            {tools.slice(0, 3).map((tool) => (
              <div className="rounded-md border border-border p-3" key={tool.toolName}>
                <p className="truncate text-sm font-medium">{tool.toolName}</p>
                <p className="mt-2 font-mono text-lg">{formatNumberBR(tool.totalCalls)}</p>
                <p className="text-xs text-muted-foreground">calls</p>
              </div>
            ))}
            {!tools.length ? <EmptyState description="Nenhuma tool retornou dados." title="Sem destaques" /> : null}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <SectionHeader description="Performance, falha, handoff e custo por ferramenta." title="Desempenho por tool" />
        </CardHeader>
        <CardContent>
          {tools.length ? <ToolsTable items={tools} /> : <EmptyState description="Nenhuma tool encontrada para os filtros atuais." title="Sem tools" />}
        </CardContent>
      </Card>
    </div>
  )
}
