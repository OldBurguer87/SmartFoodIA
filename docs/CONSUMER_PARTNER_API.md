# API de Parceiro do Consumer

## Visão geral

O Consumer consulta a API do SmartFoodIA. Cada loja possui:

- slug próprio na URL;
- token próprio;
- merchant ID;
- merchant name.

O token é armazenado somente como SHA-256, nunca em texto puro.

Para o piloto da Old Burguer 87, a base pública oficial é:

```text
https://smartfoodia.com.br
```

## Configurar a loja

Depois das migrations, use **somente o provisionador oficial**:

```bash
docker compose exec api python -m app.scripts.configure_consumer_partner \
  --store-slug old-burguer-87 \
  --merchant-id ID_FORNECIDO_PELO_CONSUMER \
  --merchant-name "Old Burguer 87" \
  --base-url https://smartfoodia.com.br
```

Guarde o token retornado pelo comando. O valor em texto puro deve ser tratado como segredo; o banco mantém somente o hash necessário à validação.

`configure_consumer_integration` é legado e não deve mais ser usado na homologação.

## URLs para cadastrar no Consumer

### Polling

```text
GET https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/events
```

### Detalhes do pedido

```text
GET https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}
```

### Evento do pedido

```text
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/events
```

### Atualização de status

```text
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/status
```

## Autenticação

```http
Authorization: Bearer TOKEN_DA_LOJA
```

## Fluxo

1. O checkout cria `PLACED / PLC`.
2. O Consumer consulta o polling.
3. O Consumer consulta os detalhes.
4. O Consumer envia `ODR` quando aplicável ao fluxo.
5. O SmartFoodIA registra o evento recebido e evita reprocessamento indevido.
6. Alterações de status no Consumer atualizam o status interno.
7. O canal de atendimento pode então notificar o cliente.

## Status suportados

- `CONFIRMED`
- `CANCELLED`
- `READY_TO_PICKUP`
- `READY`
- `DISPATCHED`
- `OUT_FOR_DELIVERY`
- `CONCLUDED`
- `DELIVERED`

## Princípio de arquitetura

O Consumer é um adaptador do SmartFoodIA, não o núcleo do produto. Regras de cliente, carrinho, pedido, cálculo, idempotência e validação permanecem no Core para permitir outros ERPs no futuro sem reescrever o sistema.
