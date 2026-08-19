import { LogOut, Moon, Sun } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Outlet, useLocation, useNavigate } from "react-router-dom"

import { DashboardFilterBar } from "@/components/filters/dashboard-filter-bar"
import { MobileNavigation, SidebarNavigation } from "@/components/navigation/navigation"
import { Button } from "@/components/ui/button"
import { useTheme } from "@/app/providers/theme-provider"
import { useLogoutMutation, useSessionQuery } from "@/features/auth/use-auth"
import { useDashboardPreferences } from "@/features/shared-dashboard/dashboard-preferences"
import { useOperationalReportMutation, useSyncCostsMutation } from "@/hooks/use-dashboard-queries"

function titleFromPath(pathname: string) {
  if (pathname.includes("diagnostics")) {
    return "Diagnóstico"
  }
  if (pathname.includes("audit")) {
    return "Auditoria"
  }
  if (pathname.includes("admin/users")) {
    return "Administração de usuários"
  }
  return "Visão Geral"
}

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const session = useSessionQuery()
  const { filters, setFilters, setLastRoute, clearDashboardPreferences } = useDashboardPreferences()
  const { theme, setTheme } = useTheme()
  const syncMutation = useSyncCostsMutation()
  const reportMutation = useOperationalReportMutation()
  const logoutMutation = useLogoutMutation(clearDashboardPreferences)
  const [notice, setNotice] = useState<{ tone: "success" | "error"; message: string } | null>(null)
  const principal = session.data?.authenticated ? session.data.principal : null
  const isAdmin = principal?.role === "platform_admin"

  useEffect(() => {
    setLastRoute(location.pathname)
  }, [location.pathname, setLastRoute])

  useEffect(() => {
    if (!principal || principal.role === "platform_admin" || !principal.tenantIds.length) return
    if (!filters.tenantId || !principal.tenantIds.includes(filters.tenantId)) {
      setFilters({ ...filters, tenantId: principal.tenantIds[0] })
    }
  }, [filters, principal, setFilters])

  useEffect(() => {
    if (!notice) return
    const timeout = window.setTimeout(() => setNotice(null), 5000)
    return () => window.clearTimeout(timeout)
  }, [notice])

  function refreshPage() {
    window.dispatchEvent(new CustomEvent("ops-refresh-active-page"))
  }

  async function handleLogout() {
    await logoutMutation.mutateAsync()
    navigate("/login", { replace: true })
  }

  async function handleFilterChange(nextFilters: typeof filters) {
    if (nextFilters.tenantId !== filters.tenantId) {
      await queryClient.cancelQueries()
      queryClient.removeQueries({
        predicate: (query) =>
          ["health", "overview", "costs", "tools", "resilience", "audit-summary", "audit-recent"].includes(
            String(query.queryKey[0]),
          ),
      })
    }
    setFilters(nextFilters)
  }

  return (
    <div className="flex min-h-screen bg-background dashboard-grid">
      <SidebarNavigation isAdmin={isAdmin} />
      <div className="flex min-w-0 flex-1 flex-col pb-16 lg:pb-0">
        <header className="flex min-h-16 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur lg:px-6">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Integrix Ops Console</p>
            <h1 className="mt-1 text-lg font-semibold tracking-normal">{titleFromPath(location.pathname)}</h1>
          </div>
          <div className="flex items-center gap-2">
            <Button
              aria-label="Alternar tema"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              size="icon"
              type="button"
              variant="ghost"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
            <Button aria-label="Sair" disabled={logoutMutation.isPending} onClick={handleLogout} size="icon" type="button" variant="ghost">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>
        <DashboardFilterBar
          filters={filters}
          onChange={handleFilterChange}
          onRefresh={refreshPage}
          onSync={() =>
            syncMutation.mutate(undefined, {
              onSuccess: (result) =>
                setNotice({
                  tone: "success",
                  message: `Sync concluído: ${result.result.created} criadas, ${result.result.updated} atualizadas, ${result.result.missingCost} sem custo, ${result.result.unresolvedTenant} em quarentena e ${result.result.missingFx} sem PTAX.`,
                }),
              onError: () => setNotice({ tone: "error", message: "O sync de custos falhou. Consulte o diagnóstico." }),
            })
          }
          onExportReport={(periodDays) =>
            reportMutation.mutate(
              { filters, periodDays },
              {
                onSuccess: () => setNotice({ tone: "success", message: "Relatório financeiro gerado." }),
                onError: () => setNotice({ tone: "error", message: "O relatório não pôde ser gerado com dados frescos." }),
              },
            )
          }
          refreshing={false}
          syncing={syncMutation.isPending}
          exporting={reportMutation.isPending}
          isAdmin={isAdmin}
          allowedTenants={principal?.tenantIds || []}
        />
        {notice ? (
          <div
            className={`mx-4 mt-3 rounded-md border px-4 py-3 text-sm lg:mx-6 ${
              notice.tone === "success"
                ? "border-success/40 bg-success/10"
                : "border-destructive/40 bg-destructive/10 text-destructive"
            }`}
          >
            {notice.message}
          </div>
        ) : null}
        <main className="min-w-0 flex-1 px-4 py-4 lg:px-6">
          <Outlet />
        </main>
      </div>
      <MobileNavigation isAdmin={isAdmin} />
    </div>
  )
}
