# Adaptador modular Consumer Partner API

O Core cria pedidos com `READY_FOR_INTEGRATION` e um evento neutro pendente. O Consumer permanece apenas um adaptador que traduz esse pedido para o contrato externo.

## Módulos

- `app/integrations/contracts`: portas neutras para qualquer ERP;
- `app/integrations/consumer`: autenticação, mapeamento, status e adaptador Consumer;
- `app/services/consumer_partner.py`: fachada usada pelos endpoints HTTP.

## Rotas atuais

- Polling: `GET /api/v1/integrations/consumer/{store_slug}/events`
- Detalhes: `GET /api/v1/integrations/consumer/{store_slug}/orders/{order_id}`
- Evento ODR: `POST /api/v1/integrations/consumer/{store_slug}/orders/{order_id}/events`
- Status homologado: `POST /api/v1/integrations/consumer/{store_slug}/orders/status`
- Status com UUID no caminho: `POST /api/v1/integrations/consumer/{store_slug}/orders/{order_id}/status`
- Compatibilidade de detalhes do runtime: `POST /api/v1/integrations/consumer/{store_slug}/orders/details`

## Autenticação

Todas as rotas protegidas aceitam token da loja via:

```text
Authorization: Bearer <token>
```

ou:

```text
xapikey: <token>
```

O Consumer real homologado utilizou `xapikey`.

## Status

O adaptador converte os estados externos para estados internos neutros. A produção também normaliza variantes CamelCase e diferenças de hífens, espaços e underscores.

Aliases aceitos incluem:

- `READY_TO_PICKUP` e `READY_FOR_PICKUP` → `READY`;
- `OUT_FOR_DELIVERY` → `DISPATCHED`;
- `DELIVERED` → `CONCLUDED`.

## Payload de delivery

O baseline homologado utiliza `deliveredBy: "Partner"` e inclui `formattedAddress`, `coordinates` e `delivery.observations`.

Produtos e complementos sem código PDV em `externalCode` continuam sendo rejeitados antes de chegar ao Consumer.

## Estado de versionamento

A auditoria de 2026-08-11 encontrou hotfixes do adaptador em uso na VPS que ainda não estavam commitados no commit base. Consulte `docs/PRODUCTION_RUNTIME.md` antes de qualquer novo deploy.
