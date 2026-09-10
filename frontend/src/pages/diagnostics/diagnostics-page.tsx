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
import { formatDateTimeBR, formatDurationMs, formatNumberBR, formatPercent } from "@/lib/format"
import { mergeVoiceQualitySeries } from "./voice-quality-series"

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

  const voiceQualitySeries = mergeVoiceQualitySeries(
    resilience.series.turnLatencyAverageMs,
    resilience.series.assistantInterruptions,
  )

  return (
    <div className="space-y-4">
      {health.sync.lastError ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Último erro do sync: {health.sync.lastError}
        </div>
      ) : null}
      {resilience.upstreamFailures.auth > 0 ? (
        <div className="rounded-md border border-destructive/60 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Alerta crítico: {formatNumberBR(resilience.upstreamFailures.auth)} ocorrência(s) de autenticação no upstream.
        </div>
      ) : null}
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={ShieldCheck} label="Saúde" tone={health.healthState === "critical" ? "danger" : health.healthState === "warning" ? "warning" : "success"} value={healthLabel(health.healthState)} />
        <StatCard detail={`${syncLabel(health.sync.freshnessState)} · ${formatDateTimeBR(health.sync.lastSyncedAt)}`} icon={Repeat} label="Lag do sync" value={health.sync.freshnessSeconds == null ? "Sem histórico" : `${Math.round(health.sync.freshnessSeconds / 60)} min`} />
        <StatCard icon={GitPullRequest} label="Idempotency hits" value={formatNumberBR(resilience.summary.idempotencyHits)} />
        <StatCard icon={AlertTriangle} label="Erros repetidos" tone={resilience.summary.repeatedBusinessErrors > 0 ? "warning" : "default"} value={formatNumberBR(resilience.summary.repeatedBusinessErrors)} />
      </section>

      {health.sync.lastRunStats ? (
        <Card>
          <CardHeader>
            <SectionHeader description="Contadores da última execução bem-sucedida." title="Último sync financeiro" />
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {[
              ["Processadas", health.sync.lastRunStats.processed],
              ["Criadas", health.sync.lastRunStats.created],
              ["Atualizadas", health.sync.lastRunStats.updated],
              ["Sem custo", health.sync.lastRunStats.missingCost],
              ["Quarentena", health.sync.lastRunStats.unresolvedTenant],
              ["Sem PTAX", health.sync.lastRunStats.missingFx],
              ["Erros", health.sync.lastRunStats.errors],
            ].map(([label, value]) => (
              <div className="rounded-md border border-border p-3" key={String(label)}>
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="mt-2 font-mono text-xl">{formatNumberBR(Number(value))}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <SectionHeader description="Timeouts e indisponibilidades de upstream por bucket." title="Falhas técnicas por período" />
          </CardHeader>
          <CardContent>
            {resilience.series.technicalFailureEvents.length ? (
              <ResponsiveLineChart
                data={resilience.series.technicalFailureEvents}
                series={[{ key: "value", label: "Falhas técnicas", color: "hsl(var(--destructive))", area: true }]}
              />
            ) : (
              <EmptyState description="Nenhum bucket com falha técnica foi encontrado." title="Sem falhas técnicas" />
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
              {formatNumberBR(health.counters.callsWithCost)} de {formatNumberBR(health.counters.vapiCalls)} calls Vapi com custo.
            </p>
            {health.counters.callsWithoutCost > 0 ? (
              <p className="mt-1 text-xs text-warning">{formatNumberBR(health.counters.callsWithoutCost)} sem custo reportado.</p>
            ) : null}
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
            <SectionHeader description="Chamadas distintas por etapa, sem recontar eventos repetidos." title="Funil de busca de rede" />
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[
              ["Tentativas", resilience.searchFunnel.attemptedCalls],
              ["Bloqueadas", resilience.searchFunnel.blockedCalls],
              ["Upstream acessado", resilience.searchFunnel.upstreamStartedCalls],
              ["Concluídas", resilience.searchFunnel.completedCalls],
              ["Com prestadores", resilience.searchFunnel.providerResultCalls],
              ["Resultado reutilizado", resilience.searchFunnel.reusedResultCalls],
            ].map(([label, value]) => (
              <div className="rounded-md border border-border p-3" key={String(label)}>
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="mt-2 font-mono text-xl">{formatNumberBR(Number(value))}</p>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <SectionHeader description="Bloqueios e falhas externas por período." title="Recuperação de busca" />
          </CardHeader>
          <CardContent>
            <ResponsiveLineChart
              data={mergeSearchSeries(resilience.series.blocks, resilience.series.successes, resilience.series.externalFailures)}
              series={[
                { key: "blocks", label: "Bloqueios", color: "hsl(var(--warning))" },
                { key: "successes", label: "Sucessos", color: "hsl(var(--success))", area: true },
                { key: "externalFailures", label: "Falhas externas", color: "hsl(var(--destructive))" },
              ]}
            />
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <SectionHeader description="Agregados preservados sem artefatos, mensagens ou transcrições." title="Qualidade de voz" />
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {[
              ["Calls com métricas", formatNumberBR(resilience.voiceQuality.callsWithMetrics)],
              ["Latência média por turno", resilience.voiceQuality.averageTurnLatencyMs == null ? "Sem dados" : formatDurationMs(resilience.voiceQuality.averageTurnLatencyMs)],
              ["Interrupções do assistente", formatNumberBR(resilience.voiceQuality.totalAssistantInterruptions)],
              ["Calls com interrupção", formatNumberBR(resilience.voiceQuality.callsWithAssistantInterruptions)],
            ].map(([label, value]) => (
              <div className="rounded-md border border-border p-3" key={String(label)}>
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="mt-2 font-mono text-xl">{value}</p>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <SectionHeader description="Latência média e interrupções por período da janela atual." title="Tendência de qualidade" />
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs text-muted-foreground">Latência média por turno (ms)</p>
            {resilience.series.turnLatencyAverageMs.length ? (
              <ResponsiveLineChart
                data={voiceQualitySeries}
                series={[
                  { key: "latency", label: "Latência média (ms)", color: "hsl(var(--primary))", area: true },
                ]}
              />
            ) : (
              <EmptyState description="Nenhuma latência foi reportada na janela." title="Sem dados de latência" />
            )}
            <p className="text-xs text-muted-foreground">Interrupções do assistente</p>
            {resilience.series.assistantInterruptions.length ? (
              <ResponsiveLineChart
                data={voiceQualitySeries}
                series={[
                  { key: "interruptions", label: "Interrupções", color: "hsl(var(--warning))" },
                ]}
              />
            ) : (
              <EmptyState description="Nenhuma contagem de interrupções foi reportada na janela." title="Sem dados de interrupções" />
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <SectionHeader description="Tools ordenadas por timeout ou indisponibilidade de upstream." title="Piores falhas técnicas" />
          </CardHeader>
          <CardContent>
            {resilience.topFailureTools.length ? <ToolsTable items={resilience.topFailureTools} /> : <EmptyState description="Sem tools com falha técnica na janela." title="Sem falhas técnicas" />}
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

function mergeSearchSeries(
  blocks: Array<{ timestamp: string; value: number }>,
  successes: Array<{ timestamp: string; value: number }>,
  externalFailures: Array<{ timestamp: string; value: number }>,
) {
  const points = new Map<string, { timestamp: string; blocks: number; successes: number; externalFailures: number }>()
  for (const [items, key] of [[blocks, "blocks"], [successes, "successes"], [externalFailures, "externalFailures"]] as const) {
    for (const item of items) {
      const existing = points.get(item.timestamp) || { timestamp: item.timestamp, blocks: 0, successes: 0, externalFailures: 0 }
      points.set(item.timestamp, { ...existing, [key]: item.value })
    }
  }
  return [...points.values()].sort((left, right) => left.timestamp.localeCompare(right.timestamp))
}
