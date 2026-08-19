import { AlertCircle, Database, ShieldAlert } from "lucide-react"

import { Skeleton } from "@/components/ui/skeleton"
import { isApiError, type ApiError } from "@/lib/api/errors"

type StatePanelProps = {
  title: string
  description: string
  variant?: "default" | "danger" | "warning"
}

export function EmptyState({ title, description }: StatePanelProps) {
  return (
    <div className="flex min-h-32 items-center gap-3 rounded-md border border-dashed border-border bg-muted/20 p-5">
      <Database className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  )
}

export function ErrorState({ error }: { error: unknown }) {
  const apiError: ApiError | null = isApiError(error) ? error : null
  const isTenantRequired = apiError?.kind === "tenant-required"
  const isForbidden = apiError?.kind === "forbidden"
  const Icon = isForbidden ? ShieldAlert : AlertCircle

  return (
    <div className="flex min-h-32 items-center gap-3 rounded-md border border-destructive/40 bg-destructive/10 p-5">
      <Icon className="h-5 w-5 text-destructive" aria-hidden="true" />
      <div>
        <p className="text-sm font-medium">
          {isTenantRequired ? "Tenant obrigatório" : isForbidden ? "Acesso negado" : "Falha operacional"}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          {apiError?.message || "Não foi possível carregar os dados desta área."}
        </p>
      </div>
    </div>
  )
}

export function PanelSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton className="h-12 w-full" key={index} />
      ))}
    </div>
  )
}
