# Desenvolvimento E Validacao

Use este guia para escolher validacoes proporcionais ao tipo de mudanca. O
repositorio usa testes `unittest`.

## Setup Basico

- Instale dependencias com `pip install -r requirements.txt` quando o ambiente
  ainda nao estiver preparado.
- Configure variaveis a partir de `.env.example` ou `.env.production.example`
  conforme o ambiente de teste.
- O entrypoint local e `app/main.py`.

## Comandos Por Area

### Validacao ampla

```powershell
venv\Scripts\python.exe -m unittest discover -s tests
```

Use quando a mudanca for transversal, tocar contratos compartilhados ou alterar
persistencia.

### Dispatch, tenant e tools

```powershell
venv\Scripts\python.exe -m unittest discover -s tests -p "test_tool_dispatcher.py"
venv\Scripts\python.exe -m unittest discover -s tests -p "test_tools_route.py"
venv\Scripts\python.exe -m unittest discover -s tests -p "test_tenant.py"
```

Use para mudancas em `/tools`, tenant resolution, registry, contracts,
idempotencia ou implementacoes tenant-aware.

### Dashboard, ops e custos

```powershell
venv\Scripts\python.exe -m unittest discover -s tests -p "test_dashboard_route.py"
venv\Scripts\python.exe -m unittest discover -s tests -p "test_vapi_cost_sync.py"
```

Use para dashboard, endpoints ops, auth ops, sync de custos, retention ou
agregacoes operacionais.

### Compatibilidade de imports

```powershell
venv\Scripts\python.exe -m unittest discover -s tests -p "test_shims.py"
venv\Scripts\python.exe -m unittest discover -s tests -p "test_main_import.py"
```

Use quando alterar `app/services`, top-level `app/api/*`, imports de entrada ou
documentacao que instrua agentes a mexer nesses caminhos.

### Persistencia e migrations

```powershell
venv\Scripts\python.exe -m unittest discover -s tests -p "test_db.py"
```

Use junto com uma revisao manual de `app/models` e `alembic/versions` quando
alterar schema, indices, constraints ou modelos SQLAlchemy.

## Regras De Edicao

- Comece pelo menor teste relevante antes da suite ampla.
- Nao rode formatadores que reescrevem arquivos sem necessidade.
- Atualize docs quando uma regra arquitetural ou comando mudar.
- Preserve shims de compatibilidade salvo tarefa explicita de remocao.
- Para mudancas tenant-sensitive, adicione teste negativo de isolamento.

## Quando Nao Rodar Tudo

Mudancas puramente documentais podem ser validadas com leitura, checagem de
links e, quando tocarem instrucoes de compatibilidade/imports, com:

```powershell
venv\Scripts\python.exe -m unittest discover -s tests -p "test_main_import.py"
venv\Scripts\python.exe -m unittest discover -s tests -p "test_shims.py"
```
