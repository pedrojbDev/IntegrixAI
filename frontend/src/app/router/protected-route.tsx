import { Navigate, Outlet, useLocation } from "react-router-dom"

import { PanelSkeleton } from "@/components/feedback/state-panels"
import { useSessionQuery } from "@/features/auth/use-auth"

export function ProtectedRoute() {
  const location = useLocation()
  const session = useSessionQuery()

  if (session.isLoading) {
    return (
      <div className="min-h-screen bg-background p-6">
        <PanelSkeleton rows={8} />
      </div>
    )
  }

  if (!session.data?.authenticated) {
    return <Navigate replace state={{ from: location }} to="/login" />
  }

  if (session.data.principal.mustChangePassword && location.pathname !== "/change-password") {
    return <Navigate replace to="/change-password" />
  }
  if (!session.data.principal.mustChangePassword && location.pathname === "/change-password") {
    return <Navigate replace to="/" />
  }

  return <Outlet />
}
