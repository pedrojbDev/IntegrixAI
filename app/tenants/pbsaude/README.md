# Implementacao PB Saude

Este diretorio concentra comportamento, vocabulario e integracoes especificas da
PB Saude. Leia este guia para mudar tools, workflows, catalogo, provider externo,
traducao da rede credenciada ou texto apresentado ao assistente.

## Limites

- `tool_handlers.py` registra handlers no implementation key `pbsaude`.
- `policies.py` define quais tools sao realmente habilitadas.
- `contracts.py` define requests, responses e o modelo de prestador.
- `workflows` valida e orquestra cada caso de uso.
- `integration` contem auth, HTTP, retries, providers, traducao e texto de fala.
- `catalog.py` resolve especialidades informais para valores canonicos.

Nao mova regras PB Saude para `app/core`. Compartilhe apenas capacidades que
tenham contrato de plataforma comprovado. Tenant e `call_id` devem continuar
explicitos ate o provider.

## Fluxo De `search_providers`

1. `workflows/search_providers.py` valida CPF, cidade e especialidade.
2. O catalogo resolve a especialidade canonica sem usar a forma sem acentos como
   texto de saida.
3. `integration/external_api_provider.py` monta a chamada tenant-aware, aplica
   autenticacao, timeout e retries limitados.
4. `integration/translator.py` converte `prestadores` em contratos `Provider`.
5. O workflow devolve `SearchProvidersResponse`; o dispatcher preserva o
   envelope Vapi `{"results": [...]}`.

Erros de negocio devem permanecer diferenciados de indisponibilidade e timeout.
Nunca registre CPF completo, credenciais externas ou payloads com PII sem
mascaramento.

O request upstream de busca envia `cpf`, `especialidade`, `cidade` e, quando
informado, `tipoAtendimento`. `bairro` permanece aceito somente como entrada
legada da Vapi durante a migracao, mas deve ser ignorado pelo workflow e nunca
enviado ao provider. O bairro devolvido dentro de cada prestador continua sendo
parte valida do endereco de resposta.

## Politica De Prestadores Por Cidade

`provider_policy.json` contem a lista versionada e tenant-scoped de prestadores
curados pela PB Saude. `provider_policy.py` valida e aplica a configuracao
somente quando `PBSAUDE_PROVIDER_POLICY_ENABLED=true`, depois de uma resposta
bem-sucedida do provider externo e antes do `SearchProvidersResponse`.

Uma especialidade configurada usa o modo da cidade (`exclusive`, `priority` ou
`ensure`). Especialidades nao configuradas preservam os resultados da API. O
fallback estatico nunca contorna CPF invalido, erro de negocio, timeout ou
indisponibilidade upstream. Servicos `online` omitem endereco e bairro no
contrato devolvido e preservam o telefone confirmado pelo cliente.

O `tenant_id` precisa constar explicitamente em `tenant_ids`; a flag sozinha nao
habilita a politica para outro tenant. Logs de avaliacao registram contagens e a
versao da policy, sem CPF, endereco ou telefone.

## Texto Para Fala E Enderecos

`integration/speech_text.py` normaliza Unicode e aplica somente correcoes
deterministicas de acentuacao. Use limites de palavra e preserve textos ja
acentuados. Nao tente adivinhar nomes proprios genericamente.

Para logradouros, a precedencia e:

1. prefixo ja presente, expandindo abreviacoes conhecidas;
2. `tipoLogradouro`, `tipo_logradouro`, `streetType` ou `street_type` do upstream;
3. override PB Saude restrito por cidade, bairro e nome da via;
4. texto original quando o tipo nao puder ser provado.

Nao use `Rua` como fallback universal. Overrides novos exigem evidencia do
logradouro e teste negativo fora da localidade para evitar homonimos.

## Validacao Focal

Escolha o menor conjunto correspondente:

```text
python -m unittest discover -s tests -p "test_search_providers_workflow.py"
python -m unittest discover -s tests -p "test_external_api_provider.py"
python -m unittest discover -s tests -p "test_provider_translator.py"
```

Mudancas em registro, tenant ou envelope tambem exigem os testes de registry,
tenant, dispatcher e rota `/tools`. Cubra entrada invalida, resposta upstream
inesperada, timeout, retry, preservacao de Unicode e ausencia de inferencia fora
do escopo conhecido.
