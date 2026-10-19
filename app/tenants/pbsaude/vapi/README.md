# Fluxo de conversa PB Saúde

`prompt.md` é a versão v18 candidata da mitigação do fluxo de Rede Credenciada.
A versão do manifest é `pbsaude-flow-v18-mitigation`. A configuração
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
saída é privado e deve ser novo. O snapshot permanece intacto. `desired.json`
contém o modelo completo com mensagens e anexos de tools alterados, os hooks
preservados mais os avisos de silêncio e `silenceTimeoutSeconds=90`.
`rollback.json` restaura os três campos de topo: `model`, `hooks` e
`silenceTimeoutSeconds`. Voz, transcrição, DTMF, destinos, interrupções e duração
máxima não entram no PATCH; ausência de `maxDurationSeconds` continua ausente.

`manifest.json` identifica o assistente, a revisão `expected_updated_at` e os
hashes de todos os campos tocados em `expected_fields_sha256`. Cada hash usa
`fingerprint({"present": true, "value": valor})`, ou
`fingerprint({"present": false})` se o campo estava ausente. Antes de uma
publicação autorizada, comparar um GET novo com a revisão e **todos** esses
hashes; divergência exige novo snapshot e revisão. Após publicar, verificar
`desired_fields_sha256` e guardar o novo `updatedAt`. Para rollback, exigir
esses hashes e a revisão pós-publicação revisada, como indicado em
`rollback_preconditions`; a revisão anterior não serve para autorizar rollback.
O gerador prepara pré-condições locais; não faz GET, PATCH ou validação remota.
`touched_fields` enumera os campos de topo enviados e protegidos pelos hashes;
`changed_fields` lista somente diferenças reais, incluindo subcampos do modelo.
Gerar novamente a mesma configuração produz `changed_fields=[]`, preservando
as pré-condições de todos os campos enviados.

Se `hooks` estava ausente, o rollback envia `[]`, restaurando semanticamente a
ausência de hooks. O manifest declara isso em `absent_field_restoration`; não
promete restaurar a omissão literal do campo no GET. Omitir `hooks` no PATCH de
rollback deixaria os avisos ativos. `silenceTimeoutSeconds` ausente, nulo ou
inválido bloqueia a geração: não inferir um default nem tentar limpá-lo com
`null`. Obter uma configuração explícita revisada antes de preparar o bundle.
O gerador também recusa falta de `updatedAt`, campos de modelo desconhecidos,
hooks malformados, hooks de silêncio incompatíveis e ausência do anúncio nativo.
Hooks não relacionados são preservados; os dois hooks exatos da mitigação já
presentes não são duplicados. Snapshots incompatíveis exigem revisão manual.

## Recuperação e silêncio da mitigação

`SLOT_UNCONFIRMED` e `USER_TURN_REQUIRED` devolvem
`data.requires_user_turn=true` e uma `data.clarification_question` segura. O
assistente fala essa pergunta exatamente e espera uma nova resposta real do
beneficiário, preservando os demais dados. Repetir uma tool, reler o histórico,
ouvir ruído ou receber uma saudação não autoriza nova busca. Uma confirmação
afirmativa vale apenas para o último campo ou exame concreto perguntado.

Após duas respostas reais inválidas, `offer_handoff` tem prioridade sobre a
coleta: oferecer atendimento humano uma vez e aguardar aceitação. Se recusar,
aguardar correção explícita ou encerramento, sem repetir ofertas ou buscas.
Antes dessas regras, `stop` interrompe ações e `wait_current_search` aguarda a
busca admitida. Nenhuma dessas duas ações oferece transferência por causa de
`retryable=false`; a flag genérica só é considerada depois de excluí-las.
O CPF continua sendo recebido exclusivamente pelo teclado, com 11 dígitos e
`#`; confirmação falada ou de últimos dígitos não serve como evidência.

Os hooks nativos `customer.speech.timeout` falam somente:

| Timeout configurado | Mensagem exata |
|---|---|
| 15 segundos | Você ainda está na linha? |
| 45 segundos | Estou aguardando sua resposta para continuar. |

Cada hook tem `triggerMaxCount=1` e `triggerResetMode=onUserSpeech`. Nenhum hook
encerra ou transfere a chamada. O encerramento por silêncio fica com o timeout
nativo de 90 segundos, preservando o motivo `silence-timed-out` nas métricas.
A [documentação de idle messages da Vapi](https://docs.vapi.ai/assistants/idle-messages)
informa que os hooks são suspensos durante tools e transferências. Os limiares
são configuração, não tempos comprovados por ligação: verificar em voz o efeito
dos avisos, do processamento de áudio, das respostas e do DTMF no timeout.

## Backend e implantação

A migração `0011_vapi_conversation_state` acrescenta um JSONB vazio por padrão.
Com `VAPI_SLOT_GUARD_ENABLED=true`, eventos e histórico recebido pelo `/tools`
usam o mesmo redutor PB Saúde antes da validação. O estado contém evidências
HMAC por turno, pergunta pendente e contadores, nunca transcrição ou CPF aberto.
Identidade do turno e revisão distinguem repetição, correção e entrega duplicada.
Eventos antigos não revivem estado expirado. Overflow do histórico bloqueia
busca conservadoramente. Locks transacionais PostgreSQL isolam tenant/chamada,
inclusive na criação de estado e na deduplicação de eventos simultâneos.

`PBSAUDE_VAPI_RECOVERY_GATE_ENABLED=true` habilita separadamente a trava de
recuperação autoritativa. A implantação começa em `false`: após uma rejeição, a
busca seguinte exige evidência HMAC de um novo turno válido para o mesmo campo.
Ruído, mensagens da assistente e DTMF incidental não liberam a trava.

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
| Busca bloqueada sem nova resposta real | fala a pergunta segura e aguarda, sem repetir tool |
| Duas respostas inválidas e recusa de atendente | uma oferta; aguarda correção ou encerramento |
| Silêncio contínuo | avisos 15/45 configurados; timeout nativo 90, motivo `silence-timed-out` |
| Dígitos e `#` durante coleta e recuperação | CPF completo libera só o campo correto; medir silêncio por voz |

Testes determinísticos validam backend e preparação da configuração, não a
qualidade de reconhecimento de fala ou a aderência probabilística do modelo.

## Coordenação de buscas e correções

A migração `0012_vapi_search_execution` acrescenta o registro temporário de
execuções. Com o guard habilitado, buscas iguais na mesma chamada reutilizam o
resultado bem-sucedido, inclusive lista vazia (`data.reused_result=true`). A
assinatura HMAC considera tenant, chamada, CPF, cidade normalizada,
especialidade canônica e tipo de atendimento; o bairro legado é ignorado.
Uma solicitação explícita do paciente para consultar novamente cria uma nova
geração; repetição da tool ou reentrega do mesmo turno não cria outra busca.

Um advisory lock de sessão PostgreSQL limita a uma busca externa ativa por
chamada, inclusive entre processos. O worker síncrono mantém esse lock até o
HTTP terminar, mesmo após timeout/cancelamento do solicitante. A conexão é
reutilizada em transações curtas de reserva e conclusão, sem transação aberta
durante o HTTP. Validação, evidência e gravação usam também o lock do estado da
conversa. Correção ou encerramento anterior à conclusão descarta a resposta.
Falha ou execução indeterminada após queda do worker exige novos argumentos ou
refresh explícito; não há retry automático do mesmo pedido.

A retenção segue `VAPI_SLOT_STATE_RETENTION_HOURS` (24 horas por padrão) e a
rotina de limpeza operacional remove execuções expiradas. As entradas da busca
são armazenadas somente como HMAC; o resultado contém a rede retornada ao
paciente, sem transcrição ou CPF. O cache é temporário e não substitui a
idempotência por `tool_call_id`. SQLite usa lock local apenas para testes e
desenvolvimento; a garantia entre processos exige PostgreSQL com afinidade de
sessão (não usar pooling de transação para advisory locks de sessão).

O estado de conversa versão 2 mantém pedidos ordenados, confirmações e negações
por campo e um marcador de refresh. Confirmação de uma correção vale somente
para o campo perguntado. Rejeição ambígua suspende a evidência correspondente.
Um histórico legado sem agrupamento recuperável revoga conservadoramente o
grupo inteiro quando um pedido desse grupo é negado; um snapshot completo novo
reconstrói os grupos. `oculista` e `oculistas` resolvem para oftalmologia;
`exame de vista` retorna `data.clarification_question` para distinguir consulta
de exame específico.

Validação de concorrência em banco descartável já migrado:

```bash
VAPI_TEST_DATABASE_URL=postgresql+psycopg://... python -m unittest discover -s tests -p 'test_vapi_*postgres.py'
```

Inclui processos independentes, queda do worker, pool de uma conexão,
timeout/cancelamento, isolamento de tenant e invalidação de resultados.
