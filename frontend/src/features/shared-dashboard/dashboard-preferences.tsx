/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"

import {
  clearPreferences,
  defaultPreferences,
  loadPreferences,
  savePreferences,
  type DashboardPreferences,
} from "@/lib/storage/preferences"
import type { AuditFilters, DashboardFilters } from "@/types/dashboard"

type DashboardPreferencesContextValue = DashboardPreferences & {
  setFilters: (filters: DashboardFilters) => void
  setAuditFilters: (filters: AuditFilters) => void
  setLastRoute: (route: string) => void
  clearDashboardPreferences: () => void
}

const DashboardPreferencesContext = createContext<DashboardPreferencesContextValue | null>(null)

export function DashboardPreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState(loadPreferences)

  useEffect(() => {
    savePreferences(preferences)
  }, [preferences])

  const setFilters = useCallback((filters: DashboardFilters) => {
    setPreferences((current) => ({ ...current, filters }))
  }, [])

  const setAuditFilters = useCallback((auditFilters: AuditFilters) => {
    setPreferences((current) => ({ ...current, auditFilters }))
  }, [])

  const setLastRoute = useCallback((lastRoute: string) => {
    setPreferences((current) => (current.lastRoute === lastRoute ? current : { ...current, lastRoute }))
  }, [])

  const clearDashboardPreferences = useCallback(() => {
    clearPreferences()
    setPreferences(defaultPreferences)
  }, [])

  const value = useMemo<DashboardPreferencesContextValue>(
    () => ({
      ...preferences,
      setFilters,
      setAuditFilters,
      setLastRoute,
      clearDashboardPreferences,
    }),
    [clearDashboardPreferences, preferences, setAuditFilters, setFilters, setLastRoute],
  )

  return (
    <DashboardPreferencesContext.Provider value={value}>
      {children}
    </DashboardPreferencesContext.Provider>
  )
}

export function useDashboardPreferences() {
  const context = useContext(DashboardPreferencesContext)
  if (!context) {
    throw new Error("useDashboardPreferences must be used inside DashboardPreferencesProvider")
  }
  return context
}
