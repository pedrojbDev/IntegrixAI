import type { LucideIcon } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"

type StatCardProps = {
  label: string
  value: string
  detail?: string
  icon?: LucideIcon
  tone?: "default" | "success" | "warning" | "danger"
}

const toneClass = {
  default: "text-muted-foreground",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
}

const accentClass = {
  default: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-destructive",
}

export function StatCard({ label, value, detail, icon: Icon, tone = "default" }: StatCardProps) {
  return (
    <Card className="relative overflow-hidden bg-card/90 shadow-md shadow-background/30">
      <div className={cn("absolute inset-x-0 top-0 h-1", accentClass[tone])} />
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
          {Icon ? (
            <span className="grid h-8 w-8 place-items-center rounded-md border border-border bg-muted/45">
              <Icon className={cn("h-4 w-4", toneClass[tone])} aria-hidden="true" />
            </span>
          ) : null}
        </div>
        <div className="mt-3 truncate font-mono text-2xl font-semibold tracking-normal">{value}</div>
        {detail ? <p className="mt-2 text-xs text-muted-foreground">{detail}</p> : null}
      </CardContent>
    </Card>
  )
}
