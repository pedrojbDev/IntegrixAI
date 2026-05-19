import { useEffect } from "react"

export function useRefreshEvent(callback: () => void) {
  useEffect(() => {
    function handleRefresh() {
      callback()
    }
    window.addEventListener("ops-refresh-active-page", handleRefresh)
    return () => window.removeEventListener("ops-refresh-active-page", handleRefresh)
  }, [callback])
}
