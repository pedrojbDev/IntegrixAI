import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { formatDateTimeBR, formatDurationMs } from "@/lib/format"
import type { AuditEvent } from "@/types/dashboard"

export function AuditEventsTable({ items }: { items: AuditEvent[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Horário</TableHead>
          <TableHead>Tenant</TableHead>
          <TableHead>Tool</TableHead>
          <TableHead>Evento</TableHead>
          <TableHead>Final state</TableHead>
          <TableHead>OK</TableHead>
          <TableHead>Erro</TableHead>
          <TableHead>Tempo tool</TableHead>
          <TableHead>Call ID</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={`${item.id}-${item.callId}-${item.eventType}`}>
            <TableCell className="font-mono">{formatDateTimeBR(item.createdAt)}</TableCell>
            <TableCell>{item.tenantId}</TableCell>
            <TableCell className="font-medium">{item.toolName}</TableCell>
            <TableCell>{item.eventType}</TableCell>
            <TableCell>{item.finalState}</TableCell>
            <TableCell>
              <Badge variant={item.ok === true ? "success" : item.ok === false ? "destructive" : "secondary"}>
                {item.ok === true ? "OK" : item.ok === false ? "Falha" : "-"}
              </Badge>
            </TableCell>
            <TableCell>{item.errorCode || "-"}</TableCell>
            <TableCell className="font-mono">{formatDurationMs(item.durationMs)}</TableCell>
            <TableCell className="max-w-48 truncate font-mono">{item.callId}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
