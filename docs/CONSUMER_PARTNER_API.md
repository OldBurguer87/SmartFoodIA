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

Depois das migrations, use somente o provisionador oficial:

```bash
docker compose exec api python -m app.scripts.configure_consumer_partner \
  --store-slug old-burguer-87 \
  --merchant-id ID_FORNECIDO_PELO_CONSUMER \
  --merchant-name "Old Burguer 87" \
  --base-url https://smartfoodia.com.br
```

`configure_consumer_integration` é legado e não deve mais ser usado.

## Autenticação

O backend aceita dois formatos:

```http
Authorization: Bearer TOKEN_DA_LOJA
```

ou:

```http
xapikey: TOKEN_DA_LOJA
```

Na homologação real de 2026-08-11, o Consumer utilizou `xapikey`.

## URLs operacionais homologadas

### Polling

```text
GET https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/events
```

### Detalhes do pedido

```text
GET https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}
```

### Evento ODR

```text
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/events
```

### Atualização de status — formato observado em homologação

```text
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/status
```

O identificador do pedido vem no corpo (`OrderId`).

### Rota de compatibilidade com UUID no caminho

```text
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/status
```

Essa rota continua disponível no backend, mas não foi a forma utilizada pelo Consumer durante a homologação real.

### Compatibilidade adicional de detalhes

O runtime homologado possui também:

```text
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/details
```

Ela é uma rota de compatibilidade operacional e deve ser mantida documentada até consolidação final do contrato.

## Fluxo real observado

1. O checkout cria `PLACED / PLC`.
2. O Consumer consulta `/events`.
3. O Consumer consulta `GET /orders/{order_id}`.
4. O pedido aparece na fila do Consumer.
5. O Consumer envia mudanças de status para `/orders/status`.
6. O SmartFoodIA atualiza o estado interno e registra eventos.
7. Quando o canal WhatsApp estiver configurado, o notifier poderá enfileirar a atualização para o cliente.

Na produção homologada, a consulta dos detalhes também marca o `PLC` pendente como entregue. Portanto, o fluxo real não deve depender exclusivamente de um callback ODR posterior.

## Status aceitos

Estados internos suportados:

- `CONFIRMED`;
- `CANCELLED`;
- `READY`;
- `DISPATCHED`;
- `CONCLUDED`.

Aliases externos aceitos/normalizados incluem:

- `READY_TO_PICKUP`;
- `READY_FOR_PICKUP`;
- `OUT_FOR_DELIVERY`;
- `DELIVERED`;
- variantes CamelCase como `ReadyToPickup` e `OutForDelivery`.

A normalização de produção ignora diferenças de maiúsculas/minúsculas, hífens, espaços e underscores quando possível.

## Payload DELIVERY homologado

Para `service_mode=DELIVERY`, o baseline que foi aceito pelo Consumer em 2026-08-11 contém:

```text
deliveredBy = "Partner"
formattedAddress
coordinates.latitude
coordinates.longitude
delivery.observations
```

O conjunto foi validado em produção após um teste A/B. Não foi isolado qual campo individual é obrigatório; por isso, esses campos devem ser mantidos juntos até uma nova homologação controlada.

## Retirada homologada

Fluxo validado:

```text
PLACED → CONFIRMED → READY → CONCLUDED
```

## Delivery homologado

Fluxo validado:

```text
PLACED → CONFIRMED → DISPATCHED → CONCLUDED
```

## Segurança

O token é segredo. A Constituição determina que logs não exponham chaves ou tokens. A auditoria de 2026-08-11 identificou que o access log do Caddy pode registrar o header `xapikey` em texto. Essa não conformidade deve ser corrigida antes da produção assistida.

## Princípio de arquitetura

O Consumer continua sendo um adaptador do SmartFoodIA. Regras de cliente, carrinho, pedido, cálculo, idempotência e validação permanecem no Core.

Consulte `docs/PRODUCTION_RUNTIME.md` para o snapshot operacional auditado.
