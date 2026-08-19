import { zodResolver } from "@hookform/resolvers/zod"
import { KeyRound, ShieldCheck } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { useLocation, useNavigate } from "react-router-dom"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { useBootstrapMutation, useLoginMutation, useSessionQuery } from "@/features/auth/use-auth"
import { useDashboardPreferences } from "@/features/shared-dashboard/dashboard-preferences"
import { isApiError } from "@/lib/api/errors"
import { loginRequestSchema } from "@/lib/api/schemas"

const bootstrapSchema = loginRequestSchema.extend({
  token: z.string().min(1, "Informe o token de bootstrap."),
})

type LoginForm = z.infer<typeof loginRequestSchema>
type BootstrapForm = z.infer<typeof bootstrapSchema>

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const session = useSessionQuery()
  const loginMutation = useLoginMutation()
  const bootstrapMutation = useBootstrapMutation()
  const { lastRoute } = useDashboardPreferences()
  const [bootstrapMode, setBootstrapMode] = useState(false)
  const loginForm = useForm<LoginForm>({
    resolver: zodResolver(loginRequestSchema),
    defaultValues: { email: "", password: "" },
  })
  const bootstrapForm = useForm<BootstrapForm>({
    resolver: zodResolver(bootstrapSchema),
    defaultValues: { email: "", password: "", token: "" },
  })

  useEffect(() => {
    if (session.data?.authenticated) {
      const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || lastRoute || "/"
      navigate(session.data.principal.mustChangePassword ? "/change-password" : from, { replace: true })
    }
  }, [lastRoute, location.state, navigate, session.data])

  const activeMutation = bootstrapMode ? bootstrapMutation : loginMutation
  const errorMessage = activeMutation.error
    ? isApiError(activeMutation.error)
      ? activeMutation.error.message
      : "Não foi possível iniciar a sessão."
    : null

  return (
    <main className="grid min-h-screen place-items-center bg-background p-4 dashboard-grid">
      <Card className="w-full max-w-md bg-card/95 shadow-xl shadow-black/5">
        <CardHeader>
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
            {bootstrapMode ? <ShieldCheck className="h-5 w-5" aria-hidden="true" /> : <KeyRound className="h-5 w-5" aria-hidden="true" />}
          </div>
          <CardTitle className="text-xl">{bootstrapMode ? "Criar primeiro administrador" : "Acesso operacional"}</CardTitle>
          <CardDescription>
            {bootstrapMode
              ? "Disponível somente enquanto nenhum administrador existir."
              : "Entre com seu usuário administrativo ou acesso de cliente."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {bootstrapMode ? (
            <form className="space-y-4" onSubmit={bootstrapForm.handleSubmit((values) => bootstrapMutation.mutateAsync(values))}>
              <Field label="Email" error={bootstrapForm.formState.errors.email?.message}>
                <Input autoComplete="email" type="email" {...bootstrapForm.register("email")} />
              </Field>
              <Field label="Senha inicial" error={bootstrapForm.formState.errors.password?.message}>
                <Input autoComplete="new-password" type="password" {...bootstrapForm.register("password")} />
              </Field>
              <Field label="Token de bootstrap" error={bootstrapForm.formState.errors.token?.message}>
                <Input autoComplete="off" type="password" {...bootstrapForm.register("token")} />
              </Field>
              {errorMessage ? <p className="text-sm text-destructive">{errorMessage}</p> : null}
              <Button className="w-full" disabled={bootstrapMutation.isPending} type="submit">
                Criar administrador
              </Button>
            </form>
          ) : (
            <form className="space-y-4" onSubmit={loginForm.handleSubmit((values) => loginMutation.mutateAsync(values))}>
              <Field label="Email" error={loginForm.formState.errors.email?.message}>
                <Input autoComplete="email" type="email" {...loginForm.register("email")} />
              </Field>
              <Field label="Senha" error={loginForm.formState.errors.password?.message}>
                <Input autoComplete="current-password" type="password" {...loginForm.register("password")} />
              </Field>
              {errorMessage ? <p className="text-sm text-destructive">{errorMessage}</p> : null}
              <Button className="w-full" disabled={loginMutation.isPending} type="submit">
                Entrar
              </Button>
            </form>
          )}
          <Button
            className="mt-3 w-full"
            onClick={() => setBootstrapMode((value) => !value)}
            type="button"
            variant="ghost"
          >
            {bootstrapMode ? "Voltar ao login" : "Configuração inicial"}
          </Button>
        </CardContent>
      </Card>
    </main>
  )
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-2">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {error ? <span className="block text-sm text-destructive">{error}</span> : null}
    </label>
  )
}
