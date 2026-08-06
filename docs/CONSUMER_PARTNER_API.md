# API de Parceiro do Consumer

## Visão geral

O Consumer consulta a API do SmartFoodIA. Cada loja possui:

- slug próprio na URL;
- token próprio;
- merchant ID;
- merchant name.

O token é armazenado somente como SHA-256, nunca em texto puro.

## Configurar a loja

Depois das migrations:

```bash
docker compose exec api python -m app.scripts.configure_consumer_integration   --store-slug old-burguer-87   --merchant-id ID_FORNECIDO_PELO_CONSUMER   --merchant-name "Old Burguer 87"
```

O terminal solicitará o token sem exibi-lo.

## URLs para cadastrar no Consumer

Substitua `https://api.seudominio.com` pelo domínio real.

### Polling

```text
GET https://api.seudominio.com/api/v1/integrations/consumer/old-burguer-87/events
```

### Detalhes do pedido

```text
GET https://api.seudominio.com/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}
```

### Evento do pedido

```text
POST https://api.seudominio.com/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/events
```

### Atualização de status

```text
POST https://api.seudominio.com/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/status
```

## Autenticação

```http
Authorization: Bearer TOKEN_DA_LOJA
```

## Fluxo

1. O checkout cria `PLACED / PLC`.
2. O Consumer consulta o polling.
3. O Consumer consulta os detalhes.
4. O Consumer envia `ODR`.
5. O SmartFoodIA marca o evento PLC como entregue.
6. Alterações no Consumer atualizam o status interno.

## Status suportados

- `CONFIRMED`
- `CANCELLED`
- `READY_TO_PICKUP`
- `READY`
- `DISPATCHED`
- `OUT_FOR_DELIVERY`
- `CONCLUDED`
- `DELIVERED`
