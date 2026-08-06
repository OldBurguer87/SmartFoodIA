# Operação de tickets e base de conhecimento

## Tickets

### Listar

```text
GET /api/v1/operations/stores/{store_id}/tickets
```

Filtros:

```text
?status=OPEN
?priority=URGENT
```

### Atribuir

```text
POST /api/v1/operations/tickets/{ticket_id}/assign
```

```json
{"assigned_to": "Maria"}
```

O status passa para `IN_PROGRESS`.

### Resolver

```text
POST /api/v1/operations/tickets/{ticket_id}/resolve
```

```json
{
  "assigned_to": "Maria",
  "resolution": "Informação confirmada com a cozinha."
}
```

## Lacunas de conhecimento

### Listar

```text
GET /api/v1/operations/stores/{store_id}/knowledge-gaps
```

A ordenação prioriza as perguntas com mais ocorrências.

### Aprovar resposta

```text
POST /api/v1/operations/knowledge-gaps/{gap_id}/resolve
```

```json
{"answer": "Sim, o molho barbecue é artesanal."}
```

### Consultar resposta aprovada

```text
POST /api/v1/operations/stores/{store_id}/knowledge/search
```

## Olívia

A ferramenta `search_knowledge` foi adicionada. Ela retorna somente respostas com status `RESOLVED`. Perguntas abertas não são tratadas como verdade.
