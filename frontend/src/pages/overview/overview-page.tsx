import { Activity, BadgeDollarSign, CheckCircle2, Clock3, PhoneForwarded, PhoneOff } from "lucide-react"
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
  formatCurrencyBRL,
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
  const automatedResolutionRate = rate(overview.kpis.automatedResolutionCalls, totalCalls)
  const successfulHandoffRate = rate(overview.kpis.successfulHandoffCalls, totalCalls)
  const normalCompletionRate = rate(overview.kpis.normalCompletionCalls, totalCalls)
  const agentSuccessRate = overview.kpis.agentSuccessRatePct
  const unresolvedRate = rate(overview.kpis.unresolvedCalls, totalCalls)
  const technicalFailureRate = overview.kpis.technicalFailureRatePct
  const coverageRate = costs.summary.coveragePct
  const costPerMinute = costs.summary.totalDurationSeconds > 0
    ? costs.summary.totalCostUsd / (costs.summary.totalDurationSeconds / 60)
    : 0
  const financialVisible = costs.visibility !== "hidden"
  return (
    <div className="space-y-4">
      {costs.visibility === "admin_preview" ? (
        <div className="rounded-md border border-warning/40 bg-warning/10 px-4 py-3 text-sm">
          Prévia administrativa: custos v2 ainda não foram liberados para clientes.
        </div>
      ) : costs.visibility === "hidden" ? (
        <div className="rounded-md border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          Valores financeiros estão em reconciliação e ainda não foram liberados.
        </div>
      ) : null}
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <StatCard detail="Calls na janela atual" icon={Activity} label="Total de calls" value={formatNumberBR(totalCalls)} />
        <StatCard detail={`${formatNumberBR(overview.kpis.successfulAgentCalls)} resolvidas, encerradas ou transferidas`} icon={CheckCircle2} label="Sucesso do agente" tone="success" value={formatPercent(agentSuccessRate)} />
        <StatCard detail={`${formatNumberBR(overview.kpis.automatedResolutionCalls)} resolvidas sem humano`} icon={CheckCircle2} label="Resolução automática" tone="success" value={formatPercent(automatedResolutionRate)} />
        <StatCard detail={`${formatNumberBR(overview.kpis.normalCompletionCalls)} encerradas pelo cliente ou agente`} icon={PhoneOff} label="Encerramento normal" tone="success" value={formatPercent(normalCompletionRate)} />
        <StatCard detail={`${formatNumberBR(overview.kpis.successfulHandoffCalls)} transferências iniciadas`} icon={PhoneForwarded} label="Sucesso com handoff" tone="success" value={formatPercent(successfulHandoffRate)} />
        <StatCard detail={`${formatNumberBR(costs.summary.callsWithCost)} calls Vapi com custo`} icon={BadgeDollarSign} label="Custo Vapi em USD" value={financialVisible ? formatCurrencyUSD(costs.summary.totalCostUsd) : "Oculto"} />
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <StatCard detail={`${formatNumberBR(overview.kpis.unresolvedCalls)} sem resolução automática; inclui handoffs`} label="Não resolvida automaticamente" tone={unresolvedRate >= 20 ? "warning" : "default"} value={formatPercent(unresolvedRate)} />
        <StatCard detail={`${formatNumberBR(overview.kpis.technicalFailureEvents)} em ${formatNumberBR(overview.kpis.toolExecutionCount)} execuções`} label="Falhas técnicas da tool" tone={technicalFailureRate >= 10 ? "danger" : "default"} value={formatPercent(technicalFailureRate)} />
        <StatCard detail={`${formatNumberBR(costs.summary.callsWithoutCost)} de ${formatNumberBR(costs.summary.vapiCalls)} sem custo`} label="Cobertura Vapi" tone={coverageRate < 80 && costs.summary.vapiCalls > 0 ? "warning" : "default"} value={formatPercent(coverageRate)} />
        <StatCard detail={costs.fx.complete ? "PTAX histórica aplicada" : "Conversão parcial ou indisponível"} label="Custo em BRL" tone={costs.fx.complete ? "default" : "warning"} value={financialVisible ? formatCurrencyBRL(costs.summary.totalCostBrl) : "Oculto"} />
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
            <SectionHeader description="Volume de calls, encerramentos normais e transferências iniciadas com sucesso por bucket." title="Chamadas e handoff" />
          </CardHeader>
          <CardContent>
            {overview.series.length ? (
              <ResponsiveLineChart
                data={overview.series}
                series={[
                  { key: "calls", label: "Calls", color: "hsl(var(--primary))", area: true },
                  { key: "normalCompletions", label: "Encerramento normal", color: "hsl(var(--chart-3))" },
                  { key: "successfulHandoffs", label: "Sucesso com handoff", color: "hsl(var(--success))" },
                ]}
              />
            ) : (
              <EmptyState description="A janela selecionada ainda não possui buckets de chamada." title="Sem série temporal" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <SectionHeader description="Custos reportados pela Vapi em USD e conversão PTAX em BRL." title="Custo por período" />
          </CardHeader>
          <CardContent>
            {financialVisible && costs.series.length ? (
              <ResponsiveLineChart
                data={costs.series.map((point) => ({ ...point, usd: point.costUsd, brl: point.costBrl }))}
                series={[
                  { key: "usd", label: "USD", color: "hsl(var(--primary))", area: true },
                  { key: "brl", label: "BRL", color: "hsl(var(--success))" },
                ]}
              />
            ) : (
              <EmptyState description="Nenhum custo sincronizado para os filtros atuais." title="Sem custos" />
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.3fr_0.7fr]">
        <Card>
          <CardHeader>
            <SectionHeader description="Composição normalizada do custo oficial retornado pela Vapi." title="Composição do custo" />
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {financialVisible ? costs.breakdown.map((item) => (
              <div className="rounded-md border border-border p-3" key={item.category}>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">{item.category}</p>
                <p className="mt-2 font-mono text-base font-semibold">{formatCurrencyUSD(item.costUsd)}</p>
                <p className="text-xs text-muted-foreground">{formatPercent(item.sharePct)} do total</p>
              </div>
            )) : <p className="text-sm text-muted-foreground">Composição oculta até a liberação financeira.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <SectionHeader description="Vínculo entre eventos internos e chamadas financeiras." title="Reconciliação" />
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex justify-between gap-4"><span className="text-muted-foreground">Cobertura de vínculo</span><strong>{formatPercent(costs.reconciliation.linkageCoveragePct)}</strong></div>
            <div className="flex justify-between gap-4"><span className="text-muted-foreground">Calls operacionais</span><strong>{formatNumberBR(costs.reconciliation.operationalCalls)}</strong></div>
            <div className="flex justify-between gap-4"><span className="text-muted-foreground">Vinculadas à Vapi</span><strong>{formatNumberBR(costs.reconciliation.linkedOperationalCalls)}</strong></div>
            <div className="flex justify-between gap-4"><span className="text-muted-foreground">Ajustes de componentes</span><strong>{formatNumberBR(costs.reconciliation.componentAdjustmentCalls)}</strong></div>
            <div className="border-t border-border pt-3 text-xs text-muted-foreground">
              PTAX mais recente: {costs.fx.lastRateDate || "indisponível"}
              {costs.fx.provisionalCalls ? ` · ${costs.fx.provisionalCalls} conversões provisórias` : ""}
              {costs.fx.missingRateCalls ? ` · ${costs.fx.missingRateCalls} sem conversão` : ""}
            </div>
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
          <SectionHeader description="Performance, falhas técnicas, handoff e duração por ferramenta. Custos não são atribuídos por tool." title="Desempenho por tool" />
        </CardHeader>
        <CardContent>
          {tools.length ? <ToolsTable items={tools} /> : <EmptyState description="Nenhuma tool encontrada para os filtros atuais." title="Sem tools" />}
        </CardContent>
      </Card>
    </div>
  )
}
