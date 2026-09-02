# Fluxo de conversa PB Saúde

`prompt.md` é a versão candidata do fluxo de Rede Credenciada. A configuração
usa `search_providers`, `transfer_call_tool_PB` e `end_call_tool`. A ferramenta
legada `handoff_human` continua disponível no backend por compatibilidade,
mas é desanexada deste assistente. O anúncio da transferência permanece na
ferramenta nativa. Modelo, voz, transcrição, DTMF e interrupções são preservados.

## Preparar configuração e rollback

O gerador só lê e escreve arquivos locais; não publica na Vapi:

```bash
python scripts/prepare_vapi_flow_bundle.py /caminho/privado/snapshot.json /caminho/privado/bundle
```

O snapshot deve conter `assistant` e `tooldefs` obtidos por GET autenticado.
Não versionar snapshots, patches preenchidos ou credenciais. O diretório de
saída é privado e deve ser novo. `desired.json` contém o modelo completo com
apenas mensagens e anexos de tools alterados; `rollback.json` restaura o modelo
anterior. `manifest.json` identifica o assistente e hashes de pré-condição.
Não substituir configurações que mudaram desde o snapshot: obter outro snapshot
e revisar novamente. O gerador recusa campos de modelo desconhecidos e ausência
do anúncio nativo para evitar perder configurações silenciosamente.

## Backend e implantação

A migração `0011_vapi_conversation_state` acrescenta um JSONB vazio por padrão.
Com `VAPI_SLOT_GUARD_ENABLED=true`, eventos e histórico recebido pelo `/tools`
usam o mesmo redutor PB Saúde antes da validação. O estado contém evidências
HMAC por turno, pergunta pendente e contadores, nunca transcrição ou CPF aberto.
Identidade do turno e revisão distinguem repetição, correção e entrega duplicada.
Eventos antigos não revivem estado expirado. Overflow do histórico bloqueia
busca conservadoramente. Locks transacionais PostgreSQL isolam tenant/chamada,
inclusive na criação de estado e na deduplicação de eventos simultâneos.

Uma busca por lote é admitida; as adicionais recebem `wait_current_search` com
tentativa zero. A idempotência por tool-call ID continua válida. Isso não é uma
fila persistente de buscas: o assistente mantém os pedidos e os retoma um por
vez. Não há execução simultânea de buscas autorizada no prompt.

Argumentos inventados não apagam dados válidos nem consomem tentativas. Erros de
negócio contam o turno do usuário uma única vez. Uma busca bem-sucedida encerra
a recuperação dos dados utilizados. Transferência iniciada bloqueia novas
buscas; um status ativo posterior pode reabrir uma transferência que falhou.
Um relatório de fim é terminal e não pode ser reaberto por evento atrasado.

Implantar a migração antes da imagem e publicar o prompt depois do health e
schema verificados, seguindo `docs/production-vps.md`. A coluna é aditiva: em
rollback restaurar imagem e configuração Vapi anteriores, mantendo a coluna e
os dados. Não fazer downgrade em produção para reverter comportamento.

## Validação

```bash
python -m unittest discover -s tests -p 'test_vapi_conversation_flow.py'
python -m unittest discover -s tests -p 'test_vapi_flow_bundle.py'
# Somente um banco PostgreSQL descartável, previamente migrado:
VAPI_TEST_DATABASE_URL=postgresql+psycopg://... python -m unittest discover -s tests -p 'test_vapi_conversation_postgres.py'
```

Após publicação autorizada, validar por telefone e conferir transcrição/tools:

| Cenário | Resultado esperado |
|---|---|
| CPF e silêncio | nenhuma busca; pergunta somente pelo dado ausente |
| Cidade corrigida | usa a cidade corrigida, preservando CPF e pedido |
| Repetir a mesma cidade na recuperação | nova resposta reconhecida |
| Três pedidos, depois “todos” e “isso” | mantém os três e consulta um por vez |
| “Alô” ou pedido de espera | nenhum campo preenchido ou tentativa consumida |
| Pedido para repetir opções | repete o resultado anterior sem nova busca |
| Duas entradas incompletas de teclado | transferência nativa, um anúncio |
| Pedido explícito de atendente | transferência imediata, sem novas perguntas |
| Transferência falha e ligação permanece ativa | não alega sucesso nem transfere em ciclo |

Testes determinísticos validam backend e preparação da configuração, não a
qualidade de reconhecimento de fala ou a aderência probabilística do modelo.
