import { lazy, Suspense } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/app/layout/app-shell"
import { env } from "@/lib/env/env"

import { ProtectedRoute } from "./protected-route"
import { SessionExpiredListener } from "./session-expired-listener"

const LoginPage = lazy(() => import("@/pages/login/login-page").then((module) => ({ default: module.LoginPage })))
const OverviewPage = lazy(() => import("@/pages/overview/overview-page").then((module) => ({ default: module.OverviewPage })))
const DiagnosticsPage = lazy(() =>
  import("@/pages/diagnostics/diagnostics-page").then((module) => ({ default: module.DiagnosticsPage })),
)
const AuditPage = lazy(() => import("@/pages/audit/audit-page").then((module) => ({ default: module.AuditPage })))
const NotFoundPage = lazy(() => import("@/pages/not-found/not-found-page").then((module) => ({ default: module.NotFoundPage })))

function RouteFallback() {
  return <div className="min-h-screen bg-background" />
}

export function AppRouter() {
  return (
    <BrowserRouter basename={env.appBasename}>
      <SessionExpiredListener />
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route element={<LoginPage />} path="/login" />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route element={<OverviewPage />} index />
              <Route element={<DiagnosticsPage />} path="diagnostics" />
              <Route element={<AuditPage />} path="audit" />
            </Route>
          </Route>
          <Route element={<NotFoundPage />} path="not-found" />
          <Route element={<Navigate replace to="not-found" />} path="*" />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
