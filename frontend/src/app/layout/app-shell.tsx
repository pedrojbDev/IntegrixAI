import { LogOut, Moon, Sun } from "lucide-react"
import { useEffect } from "react"
import { Outlet, useLocation, useNavigate } from "react-router-dom"

import { DashboardFilterBar } from "@/components/filters/dashboard-filter-bar"
import { MobileNavigation, SidebarNavigation } from "@/components/navigation/navigation"
import { Button } from "@/components/ui/button"
import { useTheme } from "@/app/providers/theme-provider"
import { useLogoutMutation } from "@/features/auth/use-auth"
import { useDashboardPreferences } from "@/features/shared-dashboard/dashboard-preferences"
import { useOperationalReportMutation, useSyncCostsMutation } from "@/hooks/use-dashboard-queries"

function titleFromPath(pathname: string) {
  if (pathname.includes("diagnostics")) {
    return "Diagnóstico"
  }
  if (pathname.includes("audit")) {
    return "Auditoria"
  }
  return "Visão Geral"
}

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const { filters, setFilters, setLastRoute, clearDashboardPreferences } = useDashboardPreferences()
  const { theme, setTheme } = useTheme()
  const syncMutation = useSyncCostsMutation()
  const reportMutation = useOperationalReportMutation()
  const logoutMutation = useLogoutMutation(clearDashboardPreferences)

  useEffect(() => {
    setLastRoute(location.pathname)
  }, [location.pathname, setLastRoute])

  function refreshPage() {
    window.dispatchEvent(new CustomEvent("ops-refresh-active-page"))
  }

  async function handleLogout() {
    await logoutMutation.mutateAsync()
    navigate("/login", { replace: true })
  }

  return (
    <div className="flex min-h-screen bg-background dashboard-grid">
      <SidebarNavigation />
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
          onChange={setFilters}
          onRefresh={refreshPage}
          onSync={() => syncMutation.mutate()}
          onExportReport={(periodDays) => reportMutation.mutate({ filters, periodDays })}
          refreshing={false}
          syncing={syncMutation.isPending}
          exporting={reportMutation.isPending}
        />
        <main className="min-w-0 flex-1 px-4 py-4 lg:px-6">
          <Outlet />
        </main>
      </div>
      <MobileNavigation />
    </div>
  )
}
