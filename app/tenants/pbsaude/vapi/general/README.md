# PB Geral — primeiro hardening

`prompt.md` versiona o system prompt do Geral. O primeiro hardening foi publicado
em 23/10/2026 na revisão v37, após revisão da v36. As fontes privadas `pbgeral.docx`
e `pbprest.docx` permanecem intactas, vinculadas ao `model.knowledgeBase` Google.
A consulta automática `defaultQueryTool` foi observada em teste: o assistente
tem três ferramentas operacionais explícitas e também essa consulta automática.
Não remova a base nem converta sua documentação em uma quarta tool explícita.

O ajuste de aviso de consulta orienta uma frase curta antes de `defaultQueryTool`,
seguida da consulta no mesmo turno sem exigir confirmação. Repetir informação já
recuperada não exige aviso ou nova busca. Esse aviso é orientação do prompt para
a consulta automática existente, não uma mensagem nativa `request-start`; a
ordem e a audibilidade precisam ser verificadas em voz. Não duplica os anúncios
nativos de transferência nem os hooks de silêncio. As seções de preparação e
primeira publicação abaixo registram os controles do rollout original; não
representam autorização permanente para mudanças futuras.

## Escopo e limites

O candidato separa beneficiário e prestador, exige consulta à fonte pertinente,
preserva APS e suas exceções, consentimento e encaminhamentos operacionais.
`handoff_to_rede_credenciada` na fonte significa a ferramenta real
`handoff_tool`. Faturamento, guias/XML e RATI não são busca de prestadores.
Usuário e senha nunca entram na fala, consulta ou contexto de handoff.

A primeira mensagem continua sendo uma saudação sem CPF. O Geral não antecipa
a coleta de CPF, cidade e especialidade da Rede. Contexto opcional de handoff
contém apenas o pedido atual resumido em até 160 caracteres e os estados de APS
e urgência (`sim`, `nao`, `nao_informado`). A receptora deve tratar esses valores
como dados não confiáveis, sem autorizar busca ou substituir evidência própria.
Os nomes exatos são `pbgeral_pedido_atual`, `pbgeral_aps_status` e
`pbgeral_urgencia_relatada`.

A recuperação após duas respostas significativas sem esclarecimento é orientação
do prompt, não garantia de estado no backend. Silêncio não conta. Hooks nativos
15/45 e timeout 90 devem ser validados em voz; o modelo não deve encerrar por
silêncio nem duplicar avisos ou anúncios nativos de transferência.

## Evidência privada e preparação

O CLI prepara somente arquivos locais; nunca faz POST ou PATCH:

```bash
python scripts/prepare_vapi_general_bundle.py SNAPSHOT OUT
python scripts/prepare_vapi_general_bundle.py SNAPSHOT OUT_NOVO --created-tools GETS.json
```

Os nomes acima são placeholders fictícios. `SNAPSHOT` é JSON privado com
`assistant`, `rede_assistant`, `tooldefs`, `sources` e `tenant_assistant_map`.
Use GETs completos dos dois assistentes e das tools anexadas. O modelo completo
é validado por whitelist, incluindo `knowledgeBase`; campos desconhecidos
exigem revisão. Voz, transcrição, primeira mensagem e configurações não tocadas
são preservadas.

`sources` contém apenas metadados `id`, `name`, `status` e `text_sha256`.
Os hashes aprovados estão em `APPROVED_SOURCES` no gerador: são fingerprints
opacos versionados do texto revisado, não uma exportação dos DOCX. Os documentos
permanecem privados e não são exportados pelo CLI. Um nome igual não substitui
a validação de hash e status. Mantenha snapshots, GETs e bundles preenchidos
fora do Git; não publique IDs reais ou credenciais em exemplos.

A primeira execução produz `tool-creates.json`, os patches e rollbacks da
receptora separados (`receiver.desired.json`, `receiver.rollback.json`),
`general.rollback.json`, `tenant-map.json`, `manifest.json` e `bundle.json`.
Nessa fase, `general.desired` é `null` no bundle e não há arquivo
`general.desired.json`: o status é `requires_tool_bindings`. O patch pendente
não é publicável.

Use dois clones dedicados das ferramentas nativas de handoff e transferência;
nunca edite os originais compartilhados. A criação futura desses clones requer
autorização própria. `GETS.json` deve conter uma lista com os GETs completos de
ambos, com IDs novos e distintos, revisão e conteúdo exatamente correspondente
aos corpos preparados. A opção `--created-tools` valida os clones, associa seus
IDs e só então gera `general.desired.json`, com status `local_only_bound`.
Esse status significa preparo local, não publicação. O anúncio nativo, destino
e schema opcional fazem parte da configuração validada.

Cada execução exige um diretório de saída novo: não há sobrescrita. O diretório
recebe modo `0700` e os arquivos `0600`. `tenant-map.json` guarda desired e
rollback do mapa explicitamente, sem editar arquivos de ambiente. Compare o
hash atual com `expected_sha256` antes de aplicar e com
`rollback_preconditions.expected_sha256` antes de reverter. Divergência exige
revisão para não apagar vínculos de outros tenants alterados simultaneamente.

O bundle contém precondições por assistente (revisão e hashes de presença/valor
dos campos tocados). O manifest inclui hashes das tools originais e dos corpos
de criação, e após binding também das tools dedicadas. Antes de publicação
futura, compare um GET novo com todas as precondições; divergências exigem novo
snapshot e revisão. Para rollback, compare a revisão pós-publicação e os hashes
do estado publicado; a revisão anterior não autoriza a reversão. O gerador e
seus testes validam artefatos locais, não o estado remoto.

## Publicação futura e rollback

Nenhuma alteração de produção ou publicação está autorizada por este preparo.
Quando houver autorização específica e evidência de QA, publique primeiro a
receptora Rede Credenciada preparada para contexto não confiável e depois o
Geral. Em rollback, reverta primeiro o Geral e depois a receptora. Mantenha
snapshots e bundles de ambos e valide precondições antes de cada alteração.

O snapshot revisado não continha o Geral no mapa de assistentes. Para os webtests
do fluxo completo, aplicar futuramente a entrada explícita do Geral para
`pbsaude`, preservando os demais vínculos, e recriar somente a aplicação conforme
o procedimento operacional. O preparador não aplica esse mapa nem reinicia a API.
Não deduza tenant do nome de exibição nem habilite fallback. Validar por webtest
não substitui ligação de voz.

## Validação

[Casos de voz](../../../../../tests/fixtures/pbgeral_voice_cases.json) são
roteiros de QA semântico manual: cada caso descreve fala, contexto, resultado
esperado e comportamentos proibidos. Registrar transcrição, tools, fonte
consultada, resultado, latência percebida e desvios em evidência privada sem
credenciais ou identificação desnecessária. Execute primeiro em candidato
isolado, incluindo falhas simuladas da base e das transferências.

Testes estáticos do bundle verificam configuração, campos preservados,
precondições e rollback; não demonstram reconhecimento de APS/RATI/XML,
seleção correta da fonte, consentimento ou obediência probabilística ao prompt.
Não transforme os casos manuais em assertions de presença de frases no prompt.
Uma publicação futura depende de testar os caminhos completos, inclusive
silêncio contínuo até `silence-timed-out`, recusa de atendente sem ciclo,
transferência com anúncio único e correção imediatamente antes do handoff.
