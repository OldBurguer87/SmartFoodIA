# Conversas, mensagens e suporte humano

## Objetivo

Persistir o histórico da Olívia, registrar falhas e transformar dúvidas não respondidas
em trabalho corrigível pela equipe.

## Entidades

### Conversation

Representa uma conversa de um canal, como WhatsApp.

### Message

Armazena mensagens de cliente, Olívia, atendente ou sistema.

### HumanTicket

Registra uma solicitação de ajuda humana com categoria, prioridade e contexto.

### KnowledgeGap

Registra uma pergunta que o sistema não conseguiu responder com segurança.
Perguntas equivalentes aumentam `occurrences` em vez de criar duplicatas.

### AIEvent

Registra eventos técnicos e operacionais, como:

- execução de ferramenta;
- erro;
- timeout;
- escalação humana;
- pedido finalizado.

## Fluxo de ajuda humana

1. A Olívia chama `request_human_help`.
2. O SmartFoodIA cria um ticket.
3. Opcionalmente cria ou incrementa uma lacuna de conhecimento.
4. A equipe responde e resolve a lacuna.
5. A resposta poderá alimentar a base de conhecimento em etapa futura.

## Endpoints

```text
POST /api/v1/conversations
POST /api/v1/conversations/{conversation_id}/messages
GET  /api/v1/conversations/{conversation_id}/messages
POST /api/v1/conversations/stores/{store_id}/tickets
POST /api/v1/conversations/stores/{store_id}/knowledge-gaps
PATCH /api/v1/conversations/knowledge-gaps/{gap_id}/resolve
POST /api/v1/conversations/stores/{store_id}/events
```
