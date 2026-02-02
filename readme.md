Título: Piloto Call Center IA – Plano de Saúde – Inbound

Objetivo
Automatizar apenas:

consulta de status de guia de exames

consulta de rede credenciada
via chamadas inbound, com fallback humano obrigatório.

Escopo incluído

Inbound

1 número (DID) exclusivo do piloto

2 intents (guia e rede)

Autenticação mínima para guia (CPF + data nasc) (OTP entra depois)

Protocolo por chamada

Registro de eventos (mínimo)

Fora de escopo

diagnóstico/orientação médica

alterações cadastrais

reclamações/OUVIDORIA

cancelamento/financeiro

outbound

WhatsApp/chat/email (opcional futuro)

Critérios de sucesso do piloto

Toda chamada termina em estado conhecido

Nunca “inventa” informação (só fala o que veio do backend)

Falhas levam a fallback humano com mensagem clara

Custos controlados (limite por chamada)

Estados finais de uma chamada

RESOLVIDA_AUTOMATICO

TRANSFERIDA_HUMANO

ERRO_SISTEMA

ENCERRADA_USUARIO

Regras de transferência para humano (gatilhos)

2 falhas de autenticação

1 falha de consulta (timeout/503)

pedido fora do escopo

usuário irritado/pede atendente

qualquer “assunto médico”