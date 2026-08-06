# Adaptador modular Consumer Partner API

O Core cria pedidos com `READY_FOR_INTEGRATION` e um evento neutro pendente. O Consumer é apenas um adaptador que traduz esse pedido para o contrato externo.

## Módulos
- `app/integrations/contracts`: portas neutras para qualquer ERP.
- `app/integrations/consumer`: autenticação, mapeamento, status e adaptador Consumer.
- `app/services/consumer_partner.py`: fachada compatível com os endpoints atuais.

## URLs para cadastrar no Consumer
- Polling: `GET /api/v1/integrations/consumer/{store_slug}/events`
- Detalhes: `GET /api/v1/integrations/consumer/{store_slug}/orders/{order_id}`
- Evento ODR: `POST /api/v1/integrations/consumer/{store_slug}/orders/{order_id}/events`
- Status: `POST /api/v1/integrations/consumer/{store_slug}/orders/{order_id}/status`

Todas exigem `Authorization: Bearer <token>`.

Produtos e complementos sem código PDV em `externalCode` são rejeitados antes de chegar ao Consumer.
