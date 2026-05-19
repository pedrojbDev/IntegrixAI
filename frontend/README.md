# Integrix Ops Console

Frontend React/Vite da console operacional servida pelo FastAPI em `/dashboard`.

## Stack

- React
- Vite
- TypeScript
- Tailwind CSS
- TanStack Query
- React Hook Form
- Zod
- Recharts
- Lucide React

## Desenvolvimento

```bash
npm install
npm run dev
```

O Vite roda em `http://localhost:5173` e usa proxy para:

- `/ops`
- `/health`
- `/tools`

Por padrao, `VITE_API_BASE_URL` fica vazio e o cliente usa chamadas relativas. Defina apenas para frontend e backend em origens separadas.

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_BASENAME=/
```

## Build

```bash
npm run typecheck
npm run lint
npm run build
```

O build sai em `frontend/dist`. Em producao, o FastAPI serve a SPA em `/dashboard` e os assets em `/dashboard/assets/*`.

## Autenticacao

A tela de login envia o token para `POST /ops/session`. O token nao e salvo em `localStorage` nem `sessionStorage`; a sessao usa cookie HttpOnly.
