import { Activity, BarChart3, ClipboardList } from "lucide-react"
import { NavLink } from "react-router-dom"

import { cn } from "@/lib/utils"

const items = [
  { to: "/", label: "Visão Geral", icon: BarChart3 },
  { to: "/diagnostics", label: "Diagnóstico", icon: Activity },
  { to: "/audit", label: "Auditoria", icon: ClipboardList },
]

export function SidebarNavigation() {
  return (
    <aside className="hidden w-64 shrink-0 border-r border-border bg-card/40 lg:block">
      <div className="border-b border-border px-5 py-4">
        <p className="text-sm font-semibold">Integrix</p>
        <p className="mt-1 text-xs text-muted-foreground">Ops Console</p>
      </div>
      <nav className="space-y-1 p-3">
        {items.map((item) => (
          <NavLink
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                isActive && "bg-accent text-accent-foreground",
              )
            }
            end={item.to === "/"}
            key={item.to}
            to={item.to}
          >
            <item.icon className="h-4 w-4" aria-hidden="true" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

export function MobileNavigation() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-3 border-t border-border bg-background/95 backdrop-blur lg:hidden">
      {items.map((item) => (
        <NavLink
          className={({ isActive }) =>
            cn(
              "flex flex-col items-center gap-1 px-2 py-2 text-xs text-muted-foreground",
              isActive && "text-primary",
            )
          }
          end={item.to === "/"}
          key={item.to}
          to={item.to}
        >
          <item.icon className="h-4 w-4" aria-hidden="true" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}
