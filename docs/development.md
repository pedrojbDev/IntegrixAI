# Desenvolvimento E Validacao

Use este guia para escolher validacoes proporcionais ao tipo de mudanca. O
repositorio usa testes `unittest`.

## Setup Basico

O caminho canonico (Linux) e o mesmo para humanos e agentes. Rode a partir
da raiz do repo ou de um worktree:

```bash
./scripts/dev-setup.sh
./scripts/test.sh
```

- `./scripts/dev-setup.sh` cria `.venv` na raiz (com `python3`) se ainda
  nao existir, instala `requirements.txt` e roda `pip check`. E
  idempotente: pode rodar de novo sem medo.
- `./scripts/test.sh` usa sempre `.venv/bin/python`. Sem argumentos, roda
  a suite ampla (igual ao CI). Com argumentos, repassa ao unittest:
  `./scripts/test.sh -p "test_dashboard_route.py"`.
- `./scripts/run-local.sh` sobe o backend em `127.0.0.1:8000` com o mesmo
  ambiente seguro (mock, SQLite desabilitado e schedulers desligados). Passe
  argumentos do Uvicorn, por exemplo `./scripts/run-local.sh --reload`.
- O runner local executa `asyncio.to_thread` inline durante os testes. Isso
  evita que o pool de threads do provedor deixe agentes presos no encerramento
  do processo; chamadas externas continuam cobertas por mocks e cenários
  explícitos. Com `ALLOW_EXTERNAL_TESTS=1`, o comportamento original de
  threads é preservado para os testes PostgreSQL descartáveis.
- O runner força `ENVIRONMENT=dev`, `DATA_MODE=mock`, `DB_ENABLED=false` e
  `DATABASE_URL=sqlite://`, além de desligar schedulers. Assim, credenciais ou
  `.env` de produção não fazem a suite acessar a VPS. Testes PostgreSQL
  descartáveis são opt-in explícito com `ALLOW_EXTERNAL_TESTS=1`.
- Cada worktree tem seu proprio `.venv` (ignorado pelo git). Depois de
  criar um worktree, rode `./scripts/dev-setup.sh` uma vez la dentro.
- Python esperado: `3.12` (ver `.python-version`; o CI usa a mesma versao).
- Nao instale pacotes com `pip` global (o sistema bloqueia por PEP 668) e
  nao use `venv\Scripts\python.exe` no Linux (esse caminho e so Windows).
- Configure variaveis a partir de `.env.example` ou `.env.production.example`
  conforme o ambiente de teste.
- O entrypoint local e `app/main.py`.

No Windows (PowerShell), o equivalente manual e:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
.venv\Scripts\python.exe -m unittest discover -s tests
```

## Comandos Por Area

### Validacao ampla

```bash
./scripts/test.sh
```

Equivalente manual: `.venv/bin/python -m unittest discover -s tests`.

Use quando a mudanca for transversal, tocar contratos compartilhados ou alterar
persistencia.

### Dispatch, tenant e tools

```bash
./scripts/test.sh -p "test_tool_dispatcher.py"
./scripts/test.sh -p "test_tools_route.py"
./scripts/test.sh -p "test_tenant.py"
```

Use para mudancas em `/tools`, tenant resolution, registry, contracts,
idempotencia ou implementacoes tenant-aware.

### Dashboard, ops e custos

```bash
./scripts/test.sh -p "test_dashboard_route.py"
./scripts/test.sh -p "test_vapi_cost_sync.py"
```

Use para dashboard, endpoints ops, auth ops, sync de custos, retention ou
agregacoes operacionais.

### Compatibilidade de imports

```bash
./scripts/test.sh -p "test_shims.py"
./scripts/test.sh -p "test_main_import.py"
```

Use quando alterar `app/services`, top-level `app/api/*`, imports de entrada ou
documentacao que instrua agentes a mexer nesses caminhos.

### Persistencia e migrations

```bash
./scripts/test.sh -p "test_db.py"
```

Use junto com uma revisao manual de `app/models` e `alembic/versions` quando
alterar schema, indices, constraints ou modelos SQLAlchemy.

## Regras De Edicao

- Rode testes sempre via `./scripts/test.sh` (nunca via `python` global).
  Se `.venv` nao existir, o proprio script faz o bootstrap.

- Comece pelo menor teste relevante antes da suite ampla.
- Nao rode formatadores que reescrevem arquivos sem necessidade.
- Atualize docs quando uma regra arquitetural ou comando mudar.
- Preserve shims de compatibilidade salvo tarefa explicita de remocao.
- Para mudancas tenant-sensitive, adicione teste negativo de isolamento.

## Quando Nao Rodar Tudo

Mudancas puramente documentais podem ser validadas com leitura, checagem de
links e, quando tocarem instrucoes de compatibilidade/imports, com:

```bash
./scripts/test.sh -p "test_main_import.py"
./scripts/test.sh -p "test_shims.py"
```
