import { zodResolver } from "@hookform/resolvers/zod"
import { KeyRound } from "lucide-react"
import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { useLocation, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { useLoginMutation, useSessionQuery } from "@/features/auth/use-auth"
import { useDashboardPreferences } from "@/features/shared-dashboard/dashboard-preferences"
import { isApiError } from "@/lib/api/errors"
import { loginRequestSchema } from "@/lib/api/schemas"
import type { z } from "zod"

type LoginForm = z.infer<typeof loginRequestSchema>

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const session = useSessionQuery()
  const loginMutation = useLoginMutation()
  const { lastRoute } = useDashboardPreferences()
  const form = useForm<LoginForm>({
    resolver: zodResolver(loginRequestSchema),
    defaultValues: { token: "" },
  })

  useEffect(() => {
    if (session.data?.authenticated) {
      const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || lastRoute || "/"
      navigate(from, { replace: true })
    }
  }, [lastRoute, location.state, navigate, session.data?.authenticated])

  async function onSubmit(values: LoginForm) {
    await loginMutation.mutateAsync(values)
  }

  const errorMessage = loginMutation.error
    ? isApiError(loginMutation.error)
      ? loginMutation.error.message
      : "Não foi possível iniciar a sessão."
    : null

  return (
    <main className="grid min-h-screen place-items-center bg-background p-4 dashboard-grid">
      <Card className="w-full max-w-md bg-card/95">
        <CardHeader>
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <KeyRound className="h-5 w-5" aria-hidden="true" />
          </div>
          <CardTitle className="text-xl">Acesso operacional</CardTitle>
          <CardDescription>Informe o token ops para abrir a console Integrix.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
            <label className="space-y-2">
              <span className="text-sm font-medium">Token</span>
              <Input autoComplete="off" type="password" {...form.register("token")} />
            </label>
            {form.formState.errors.token ? (
              <p className="text-sm text-destructive">{form.formState.errors.token.message}</p>
            ) : null}
            {errorMessage ? <p className="text-sm text-destructive">{errorMessage}</p> : null}
            <Button className="w-full" disabled={loginMutation.isPending} type="submit">
              Entrar
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
