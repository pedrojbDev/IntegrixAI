import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Copy, KeyRound, UserPlus } from "lucide-react"
import { useState } from "react"

import { EmptyState, ErrorState, PanelSkeleton } from "@/components/feedback/state-panels"
import { SectionHeader } from "@/components/layout/section-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useSessionQuery } from "@/features/auth/use-auth"
import { createUser, listUsers, resetUserPassword, updateUser } from "@/lib/api/admin"
import { isApiError } from "@/lib/api/errors"
import type { OpsRole, OpsUser } from "@/types/dashboard"

type EditableUser = {
  role: OpsRole
  tenantIds: string
  isActive: boolean
}

function parseTenants(value: string) {
  return [...new Set(value.split(",").map((item) => item.trim()).filter(Boolean))].sort()
}

export function AdminUsersPage() {
  const session = useSessionQuery()
  const principal = session.data?.authenticated ? session.data.principal : null
  const queryClient = useQueryClient()
  const users = useQuery({ queryKey: ["admin-users"], queryFn: listUsers, enabled: principal?.role === "platform_admin" })
  const [email, setEmail] = useState("")
  const [role, setRole] = useState<OpsRole>("tenant_user")
  const [tenantIds, setTenantIds] = useState("")
  const [edits, setEdits] = useState<Record<string, EditableUser>>({})
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const refreshUsers = async () => {
    await queryClient.invalidateQueries({ queryKey: ["admin-users"] })
  }
  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: async (result) => {
      setTemporaryPassword(result.temporaryPassword)
      setNotice("Usuário criado. A senha abaixo será exibida apenas agora.")
      setEmail("")
      setTenantIds("")
      await refreshUsers()
    },
  })
  const updateMutation = useMutation({
    mutationFn: ({ userId, values }: { userId: string; values: EditableUser }) =>
      updateUser(userId, {
        role: values.role,
        tenantIds: parseTenants(values.tenantIds),
        isActive: values.isActive,
      }),
    onSuccess: async () => {
      setNotice("Usuário atualizado e sessões anteriores revogadas.")
      await refreshUsers()
    },
  })
  const resetMutation = useMutation({
    mutationFn: resetUserPassword,
    onSuccess: (password) => {
      setTemporaryPassword(password)
      setNotice("Senha temporária gerada. Ela será exibida apenas agora.")
    },
  })
  const error = createMutation.error || updateMutation.error || resetMutation.error
  const errorMessage = error
    ? isApiError(error)
      ? error.message
      : "Não foi possível concluir a ação administrativa."
    : null

  const userRows = (users.data || []).map((user) => ({
    user,
    edit: edits[user.id] || {
      role: user.role,
      tenantIds: user.tenantIds.join(", "),
      isActive: user.isActive,
    },
  }))

  if (principal?.role !== "platform_admin") {
    return <EmptyState title="Acesso restrito" description="Somente administradores da plataforma gerenciam usuários." />
  }
  if (users.isLoading) return <PanelSkeleton rows={8} />
  if (users.error) return <ErrorState error={users.error} />

  function setUserEdit(user: OpsUser, patch: Partial<EditableUser>) {
    setEdits((current) => ({
      ...current,
      [user.id]: {
        role: current[user.id]?.role || user.role,
        tenantIds: current[user.id]?.tenantIds ?? user.tenantIds.join(", "),
        isActive: current[user.id]?.isActive ?? user.isActive,
        ...patch,
      },
    }))
  }

  return (
    <div className="space-y-4">
      {notice ? (
        <div className="rounded-md border border-success/40 bg-success/10 px-4 py-3 text-sm">{notice}</div>
      ) : null}
      {temporaryPassword ? (
        <Card className="border-warning/50">
          <CardHeader>
            <SectionHeader
              title="Senha temporária — exibição única"
              description="Copie e entregue por um canal seguro. O usuário será obrigado a substituí-la no primeiro acesso."
            />
          </CardHeader>
          <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <code className="min-w-0 flex-1 overflow-x-auto rounded-md bg-muted px-3 py-2 text-sm">{temporaryPassword}</code>
            <Button onClick={() => navigator.clipboard.writeText(temporaryPassword)} type="button" variant="outline">
              <Copy className="h-4 w-4" aria-hidden="true" />
              Copiar
            </Button>
            <Button onClick={() => setTemporaryPassword(null)} type="button" variant="ghost">
              Ocultar
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <SectionHeader title="Novo usuário" description="Clientes precisam de pelo menos um tenant. Administradores podem operar a plataforma." />
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 lg:grid-cols-[1.2fr_0.7fr_1.2fr_auto] lg:items-end"
            onSubmit={(event) => {
              event.preventDefault()
              createMutation.mutate({ email, role, tenantIds: parseTenants(tenantIds) })
            }}
          >
            <label className="space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground">Email</span>
              <Input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground">Papel</span>
              <Select value={role} onChange={(event) => setRole(event.target.value as OpsRole)}>
                <option value="tenant_user">Cliente</option>
                <option value="platform_admin">Administrador</option>
              </Select>
            </label>
            <label className="space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground">Tenants, separados por vírgula</span>
              <Input
                placeholder="tenant-a, tenant-b"
                required={role === "tenant_user"}
                value={tenantIds}
                onChange={(event) => setTenantIds(event.target.value)}
              />
            </label>
            <Button disabled={createMutation.isPending} type="submit">
              <UserPlus className="h-4 w-4" aria-hidden="true" />
              Criar usuário
            </Button>
          </form>
          {errorMessage ? <p className="mt-3 text-sm text-destructive">{errorMessage}</p> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionHeader title="Usuários e memberships" description="Alterações revogam sessões existentes para aplicar o novo escopo imediatamente." />
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Usuário</TableHead>
                <TableHead>Papel</TableHead>
                <TableHead>Tenants</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {userRows.map(({ user, edit }) => (
                <TableRow key={user.id}>
                  <TableCell>
                    <p className="font-medium">{user.email}</p>
                    {user.mustChangePassword ? <Badge className="mt-1" variant="warning">Troca pendente</Badge> : null}
                  </TableCell>
                  <TableCell className="min-w-40">
                    <Select value={edit.role} onChange={(event) => setUserEdit(user, { role: event.target.value as OpsRole })}>
                      <option value="tenant_user">Cliente</option>
                      <option value="platform_admin">Administrador</option>
                    </Select>
                  </TableCell>
                  <TableCell className="min-w-64">
                    <Input value={edit.tenantIds} onChange={(event) => setUserEdit(user, { tenantIds: event.target.value })} />
                  </TableCell>
                  <TableCell>
                    <Button
                      onClick={() => setUserEdit(user, { isActive: !edit.isActive })}
                      size="sm"
                      type="button"
                      variant={edit.isActive ? "outline" : "destructive"}
                    >
                      {edit.isActive ? "Ativo" : "Inativo"}
                    </Button>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        disabled={updateMutation.isPending}
                        onClick={() => updateMutation.mutate({ userId: user.id, values: edit })}
                        size="sm"
                        type="button"
                      >
                        Salvar
                      </Button>
                      <Button
                        disabled={resetMutation.isPending}
                        onClick={() => resetMutation.mutate(user.id)}
                        size="sm"
                        type="button"
                        variant="outline"
                      >
                        <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
                        Resetar senha
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
