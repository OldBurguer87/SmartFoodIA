# Atendimento humano e retomada pela Olívia

## Objetivo

Permitir que um atendente assuma uma conversa sem criar uma segunda conversa e sem a Olívia responder ao mesmo tempo.

## Estados

- `OPEN`: atendimento controlado pela Olívia.
- `HUMAN`: atendimento controlado por uma pessoa.
- `CLOSED`: conversa encerrada.

## Operações

### Listar conversas

```text
GET /api/v1/operations/stores/{store_id}/conversations
```

Filtro opcional:

```text
?status=HUMAN
```

### Assumir conversa

```text
POST /api/v1/operations/conversations/{conversation_id}/takeover
```

```json
{"assigned_to": "Atendente 1"}
```

### Responder como atendente

```text
POST /api/v1/operations/conversations/{conversation_id}/reply
```

```json
{
  "assigned_to": "Atendente 1",
  "content": "Olá, vou ajudar você."
}
```

A resposta é persistida e colocada na mesma fila de saída do WhatsApp.

### Devolver para a Olívia

```text
POST /api/v1/operations/conversations/{conversation_id}/release
```

```json
{"assigned_to": "Atendente 1"}
```

## Comportamento do WhatsApp

Durante `HUMAN`:

- mensagens recebidas continuam sendo salvas;
- a Olívia não é chamada;
- nenhuma resposta automática é criada;
- o atendente responde pelo endpoint operacional.

Ao liberar, a conversa volta para `OPEN` e as próximas mensagens voltam a ser atendidas pela Olívia.
