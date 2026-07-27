import { zodResolver } from "@hookform/resolvers/zod"
import { LockKeyhole } from "lucide-react"
import { useForm } from "react-hook-form"
import { useNavigate } from "react-router-dom"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { useChangePasswordMutation } from "@/features/auth/use-auth"
import { isApiError } from "@/lib/api/errors"

const schema = z
  .object({
    currentPassword: z.string().min(8, "Informe sua senha atual."),
    newPassword: z.string().min(12, "Use pelo menos 12 caracteres."),
    confirmation: z.string(),
  })
  .refine((value) => value.newPassword === value.confirmation, {
    message: "As senhas não coincidem.",
    path: ["confirmation"],
  })

type FormValues = z.infer<typeof schema>

export function ChangePasswordPage() {
  const navigate = useNavigate()
  const mutation = useChangePasswordMutation()
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { currentPassword: "", newPassword: "", confirmation: "" },
  })

  async function submit(values: FormValues) {
    await mutation.mutateAsync({
      currentPassword: values.currentPassword,
      newPassword: values.newPassword,
    })
    navigate("/login", { replace: true })
  }

  return (
    <main className="grid min-h-screen place-items-center bg-background p-4 dashboard-grid">
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <LockKeyhole className="h-5 w-5" aria-hidden="true" />
          </div>
          <CardTitle>Defina sua senha</CardTitle>
          <CardDescription>A senha temporária precisa ser substituída antes de acessar os dados.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={form.handleSubmit(submit)}>
            <PasswordField label="Senha temporária" error={form.formState.errors.currentPassword?.message}>
              <Input autoComplete="current-password" type="password" {...form.register("currentPassword")} />
            </PasswordField>
            <PasswordField label="Nova senha" error={form.formState.errors.newPassword?.message}>
              <Input autoComplete="new-password" type="password" {...form.register("newPassword")} />
            </PasswordField>
            <PasswordField label="Confirmar nova senha" error={form.formState.errors.confirmation?.message}>
              <Input autoComplete="new-password" type="password" {...form.register("confirmation")} />
            </PasswordField>
            {mutation.error ? (
              <p className="text-sm text-destructive">
                {isApiError(mutation.error) ? mutation.error.message : "Não foi possível alterar a senha."}
              </p>
            ) : null}
            <Button className="w-full" disabled={mutation.isPending} type="submit">
              Salvar nova senha
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}

function PasswordField({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-2">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {error ? <span className="block text-sm text-destructive">{error}</span> : null}
    </label>
  )
}
