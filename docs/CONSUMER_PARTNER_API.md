# API de Parceiro do Consumer

## Visão geral

O Consumer consulta a API do SmartFoodIA. Cada loja possui:

- slug próprio na URL;
- token próprio;
- merchant ID;
- merchant name.

O token é armazenado somente como SHA-256, nunca em texto puro.

Para a Old Burguer 87, a base pública oficial é:

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

O backend aceita:

```http
Authorization: Bearer TOKEN_DA_LOJA
```

ou:

```http
xapikey: TOKEN_DA_LOJA
```

Na homologação real, o Consumer utilizou `xapikey`.

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

### Atualização de status

Formato observado em produção:

```text
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/status
```

O `OrderId` vem no corpo JSON.

Compatibilidade com UUID no caminho:

```text
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/status
```

### Compatibilidade adicional de detalhes

```text
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/details
```

## Fluxo real observado

1. O checkout cria `PLACED / PLC`.
2. O pedido passa pelas regras de liberação do Core.
3. O Consumer consulta `/events`.
4. O Consumer consulta detalhes.
5. O pedido aparece na fila do Consumer.
6. O Consumer envia mudanças de status.
7. O SmartFoodIA atualiza o estado interno e registra eventos.
8. O notifier pode enfileirar atualização para o cliente pelo WhatsApp.

## Regra de liberação para pedidos PIX

Desde o commit `832f93e`, pedidos com:

```text
payment_method = PIX
service_mode = DELIVERY ou TAKEOUT
```

**não são expostos ao Consumer imediatamente após o checkout**.

Eles só podem aparecer no polling, ser serializados em detalhes ou aceitar callbacks diretos quando existir um `PaymentReceipt` do pedido com status:

```text
AUTO_CONFIRMED
ou
HUMAN_CONFIRMED
```

Estados abaixo **não liberam o pedido**:

```text
RECEIVED
NEEDS_REVIEW
HUMAN_REJECTED
```

Essa proteção existe em duas fronteiras:

- filtro de eventos pendentes usados pelo polling;
- validação direta no adapter antes de detalhes/eventos/status.

Assim, uma chamada direta ao endpoint não consegue contornar a regra do polling.

## Pedidos agendados

Pedidos com `release_at` futuro continuam invisíveis ao Consumer até o horário de liberação.

Para PIX agendado, as duas condições precisam ser verdadeiras:

1. `release_at` já alcançado;
2. pagamento PIX confirmado (`AUTO_CONFIRMED` ou `HUMAN_CONFIRMED`).

## Pagamentos não-PIX

A trava descrita acima é exclusiva do PIX.

Meios como dinheiro, débito, crédito ou cartão mantêm o comportamento de integração existente, respeitando as demais regras do pedido.

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

A normalização ignora diferenças de maiúsculas/minúsculas, hífens, espaços e underscores quando possível.

## Payload DELIVERY homologado

Para `service_mode=DELIVERY`, o baseline aceito pelo Consumer contém endereço e bloco de entrega compatíveis com o contrato real, incluindo os campos necessários para a operação homologada.

Até uma nova homologação controlada, o mapper deve preservar o conjunto já aprovado em produção.

## Retirada homologada

```text
PLACED → CONFIRMED → READY → CONCLUDED
```

## Delivery homologado

```text
PLACED → CONFIRMED → READY → DISPATCHED → CONCLUDED
```

## Proteção contra regressão

Callbacks tardios não podem reabrir pedidos terminais nem reduzir o estágio operacional.

Exemplos bloqueados:

```text
CONCLUDED → READY
DISPATCHED → READY
READY → CONFIRMED
```

## Segurança

- tokens são segredos;
- logs não devem expor `xapikey`;
- o Consumer continua sendo um adapter;
- regras de cliente, carrinho, pagamento, pedido, idempotência e liberação permanecem no Core.

Consulte `docs/PRODUCTION_RUNTIME.md` para o snapshot operacional mais recente.
