import { useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"

export function SessionExpiredListener() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  useEffect(() => {
    function handleSessionExpired() {
      queryClient.clear()
      navigate("/login", { replace: true })
    }

    window.addEventListener("ops-session-expired", handleSessionExpired)
    return () => window.removeEventListener("ops-session-expired", handleSessionExpired)
  }, [navigate, queryClient])

  return null
}
