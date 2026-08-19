import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"

export function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-background p-6">
      <div className="max-w-md text-center">
        <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">404</p>
        <h1 className="mt-2 text-2xl font-semibold">Página não encontrada</h1>
        <p className="mt-3 text-sm text-muted-foreground">A rota solicitada não existe nesta console.</p>
        <Link to="/">
          <Button className="mt-6">Voltar para a visão geral</Button>
        </Link>
      </div>
    </main>
  )
}
