import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { formatDurationMs, formatNumberBR, formatPercent } from "@/lib/format"
import type { ToolPerformance } from "@/types/dashboard"

export function ToolsTable({ items }: { items: ToolPerformance[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Tool</TableHead>
          <TableHead>Total</TableHead>
          <TableHead>Resolução</TableHead>
          <TableHead>Falha</TableHead>
          <TableHead>Handoff</TableHead>
          <TableHead>Tempo tool</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => {
          const resolution = item.totalCalls > 0 ? (item.successCalls / item.totalCalls) * 100 : 0
          return (
            <TableRow key={item.toolName}>
              <TableCell className="font-medium">{item.toolName}</TableCell>
              <TableCell className="font-mono">{formatNumberBR(item.totalCalls)}</TableCell>
              <TableCell>
                <Badge variant="success">{formatPercent(resolution)}</Badge>
              </TableCell>
              <TableCell>
                <Badge variant={item.failureRatePct >= 10 ? "destructive" : "secondary"}>
                  {formatPercent(item.failureRatePct)}
                </Badge>
              </TableCell>
              <TableCell className="font-mono">{formatNumberBR(item.handoffCalls)}</TableCell>
              <TableCell className="font-mono">{formatDurationMs(item.avgDurationMs)}</TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
