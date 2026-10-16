# Relatorios Operacionais

Use este documento ao alterar a exportacao de PDF do dashboard ou a entrega
diaria por email. Ele complementa `runtime-flows.md`: nao replica os fluxos de
metricas nem as regras gerais de tenant.

## Limites E Componentes

- `app/api/routes/ops.py` autentica a operacao e apenas encaminha a solicitacao.
- `app/core/ops/dashboard_service.py` continua como fonte das agregacoes usadas
  pelo dashboard e pelos relatorios.
- `app/core/ops/report_service.py` transforma o resumo operacional em PDF.
- `app/core/ops/report_delivery_service.py` monta o relatorio, coordena o envio
  SMTP e registra a execucao concluida.
- `app/core/ops/report_scheduler.py` verifica a janela diaria durante o ciclo
  de vida da aplicacao; ele nao e um worker externo independente.
- `app/config.py` concentra a configuracao de periodo, horario, tenant e SMTP.

## Invariantes

1. A exportacao manual aceita somente os periodos suportados: 7, 15, 30 ou 90
   dias. Reutilize as agregacoes existentes; nao crie uma segunda definicao de
   metrica no PDF.
2. Todo relatorio e tenant-scoped. A rotina diaria exige `tenant_id` explicito,
   inclusive em ambientes onde o dashboard pode usar comportamento local de
   desenvolvimento.
3. A rotina usa `America/Sao_Paulo` e o horario configurado em
   `DAILY_REPORT_HOUR_BRASILIA` (padrao: 7). Se a aplicacao iniciar depois do
   horario, ela ainda pode executar uma vez naquele dia.
4. O lock consultivo do Postgres e o estado em `OpsSyncState` impedem execucoes
   simultaneas e repetem somente quando ainda nao existe um envio concluido para
   a data. Preserve ambos ao alterar a rotina para manter seguranca com varios
   workers.
5. Credenciais SMTP pertencem somente ao ambiente de execucao. Nunca registre
   senha, host, destinatarios ou o PDF em logs; registre apenas estado, tenant,
   data e quantidade de destinatarios quando necessario.
6. Uma falha de SMTP nao deve marcar o dia como entregue. O proximo ciclo deve
   poder tentar novamente, com a falha observavel nos logs estruturados.

## Conteudo E Layout Do PDF

- Resumo executivo: resultados do atendimento, grafico de volume e definicoes.
  Resolucao automatica usa `automated_resolution_calls`; sucesso do agente soma
  resolucoes e transferencias bem-sucedidas. Transferencias permanecem nao
  resolvidas do ponto de vista da automacao.
- Custos e consumo: USD, BRL, custo medio, cobertura, duracao, componentes e
  qualidade da conversao PTAX. Valores ausentes nao devem aparecer como zero
  confirmado. Os componentes agregados nao distinguem ausencia de valor zero;
  essa limitacao e indicada no PDF.
- Diagnostico: saude, sincronizacao global, execucoes, falhas tecnicas e tabela
  por ferramenta. As tabelas repetem o cabecalho quando continuam em outra
  pagina. Datas sao exibidas no horario de Brasilia.
- A grade tem tres cards por linha e considera margens e padding do frame A4.
  Cards permanecem inteiros; valores extensos ajustam a fonte e nomes quebram
  linha. Cada area comeca em nova pagina e tabelas extensas podem continuar.

## Configuracao Operacional

Mantenha `DAILY_REPORT_ENABLED=false` por padrao. Para habilitar em producao,
defina o tenant, destinatarios, periodo, horario e todas as variaveis SMTP
documentadas em `.env.production.example`. Os destinatarios usam lista separada
por virgula para permitir inclusoes futuras sem alterar codigo.

Nao coloque credenciais reais em `.env.example`, `.env.production.example`,
documentacao, testes ou commits. A ativacao na VPS exige configuracao segura das
variaveis de ambiente e reinicio/deploy da aplicacao.

## Validacao

Para mudancas de relatorio ou entrega, execute o menor conjunto aplicavel:

```text
./scripts/test.sh -p "test_report_layout.py"
venv\Scripts\python.exe -m unittest discover -s tests -p "test_dashboard_route.py"
venv\Scripts\python.exe -m unittest discover -s tests -p "test_dashboard_service.py"
venv\Scripts\python.exe -m unittest discover -s tests -p "test_daily_report_delivery.py"
venv\Scripts\python.exe -m unittest discover -s tests -p "test_config.py"
```

Ao mudar o layout PDF, gere um exemplo com dados sinteticos e faca a verificacao
visual renderizando as paginas. Ao mudar agendamento ou SMTP, cubra ao menos:
horario de Brasilia, tenant ausente, configuracao incompleta, falha no envio e
concorrencia entre workers.
