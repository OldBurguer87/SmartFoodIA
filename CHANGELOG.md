# Changelog

## Pós-0.3.4 — Homologação operacional de 2026-08-11

- DNS e HTTPS confirmados em produção para `smartfoodia.com.br`.
- Integração Consumer homologada para retirada e delivery.
- Confirmado uso real do header `xapikey` pelo Consumer; backend mantém compatibilidade com `Authorization: Bearer`.
- Confirmado callback de status operacional em `POST /orders/status`, com `OrderId` no corpo; rota com UUID no caminho permanece compatível.
- Adicionada em produção rota de compatibilidade `POST /orders/details`.
- Consulta `GET /orders/{order_id}` passou a marcar `PLC` pendente como entregue no runtime homologado.
- Normalização de status ajustada em produção para aceitar formatos como `ReadyToPickup`, `ReadyForPickup` e `OutForDelivery`.
- Payload DELIVERY homologado com `deliveredBy: "Partner"`, `formattedAddress`, `coordinates` e `delivery.observations`.
- Retirada validada em `PLACED → CONFIRMED → READY → CONCLUDED`.
- Delivery validado em `PLACED → CONFIRMED → DISPATCHED → CONCLUDED`.
- Auditoria da VPS confirmou OpenAI e WhatsApp implementados no código, porém ainda não configurados para produção real.
- Identificada não conformidade: access log do Caddy pode registrar `xapikey` em texto.
- Identificados hotfixes Consumer em uso na VPS ainda não consolidados no commit base do GitHub.
- Documentação atualizada para separar estado implementado, configurado e homologado.

## 0.3.4

- Alinhado o roadmap com o histórico real das versões implementadas.
- Registradas formalmente as decisões de VPS, domínio, Cloudflare, Caddy e URL pública canônica.
- Registrada a prioridade absoluta de homologar o primeiro pedido no Consumer antes de expandir escopo.
- Consolidado `configure_consumer_partner` como provisionador oficial.
- Removidas referências documentais ao script obsoleto `configure_consumer_integration`.
- Substituído `api.seudominio.com` por `smartfoodia.com.br` na documentação oficial do piloto.
- Atualizado `.env.example` para a base pública oficial da homologação.
- Nenhuma regra funcional do Core ou contrato de integração foi alterado nesta versão.

## 0.3.3

- Adicionada implantação de produção com Caddy e HTTPS automático.
- Adicionado `docker-compose.production.yml`.
- Adicionado endpoint protegido de diagnóstico Consumer.
- Adicionadas verificações de integração, merchant, token e HTTPS.
- Adicionado script externo de verificação da API pública.
- Adicionados testes de diagnóstico.
- Adicionado roteiro de homologação do primeiro pedido.

## 0.3.2

- Endurecido o contrato Consumer e removidas dependências fixas de loja.
