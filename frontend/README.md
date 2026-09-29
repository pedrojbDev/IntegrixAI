# Integrix Ops Console

Fonte da console operacional React/Vite servida pelo FastAPI em `/dashboard`.
Leia este arquivo somente para tarefas de UI ou para mudancas no contrato entre
o dashboard e os endpoints `/ops`.

## Responsabilidades

- `src/pages`: composicao das telas de login, troca de senha, overview,
  auditoria, diagnostico e administracao de usuarios.
- `src/components`: UI reutilizavel, filtros, metricas, graficos e tabelas.
- `src/hooks`: consultas TanStack Query e coordenacao de estado remoto.
- `src/lib/api`: cliente HTTP e funcoes por recurso. Componentes nao devem montar
  URLs ou repetir tratamento de erro diretamente.
- `src/types`: contratos TypeScript consumidos pela UI.
- `src/app`: providers, layout e roteamento.

Regras de negocio, tenant scope, autorizacao, agregacoes e geracao de relatorio
permanecem no backend. O frontend apresenta dados e envia filtros; nao replica
calculos operacionais.

## Dados E Autenticacao

O login envia `{email, password}` para `POST /ops/session`. A sessao opaca usa
cookie HttpOnly e mutacoes enviam o token CSRF lido do cookie nao-HttpOnly
correspondente. Nao grave sessao, senha ou token de bootstrap em `localStorage`
ou `sessionStorage`.

`OPS_DASHBOARD_TOKEN` aparece apenas no fluxo inicial de `POST /ops/bootstrap`.
Depois que existe um `platform_admin`, ele nao autentica nenhuma rota. Usuarios
`tenant_user` recebem a lista de tenants autorizados pela sessao; a UI nao deve
aceitar tenant arbitrario para esse papel.

TanStack Query controla cache, carregamento, erro e revalidacao. Filtros
compartilhados de tenant, assistant e periodo devem produzir chaves de consulta
distintas para impedir reaproveitamento de dados com outro escopo.
O periodo personalizado aceita datas inicial e final inclusivas no fuso de
Sao Paulo, com ate 366 dias, e filtra metricas e auditoria. O periodo do PDF
e escolhido separadamente.
Ao trocar tenant, consultas em andamento sao canceladas e caches de dashboard
anteriores sao descartados para evitar reaproveitamento visual.

## Desenvolvimento

```bash
npm install
npm run dev
```

O Vite roda em `http://localhost:5173` e encaminha `/ops`, `/health` e `/tools`
ao backend. Use `VITE_API_BASE_URL` apenas quando as origens forem separadas.
Em desenvolvimento o basename padrao e `/`; no build de producao ele e
`/dashboard` quando `VITE_APP_BASENAME` nao foi definido.

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_BASENAME=/
```

## Producao E Validacao

O build gera `frontend/dist`. O Dockerfile executa esse build e copia o resultado
para a imagem FastAPI, que serve a SPA em `/dashboard` e assets em
`/dashboard/assets/*`. Alteracoes no frontend exigem rebuild da imagem.

Antes de concluir uma mudanca:

```bash
npm run typecheck
npm run lint
npm run build
```

Valide login, navegacao, estados de loading/erro/vazio, filtros alterando as
query keys e o fluxo tocado na largura desktop suportada. `app/static/dashboard`
e uma superficie legada de compatibilidade, nao a fonte ativa da console.
