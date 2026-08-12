# Changelog

## Pós-0.3.4 — Homologação operacional de 2026-08-11/12

- DNS e HTTPS confirmados em produção para `smartfoodia.com.br`.
- Integração Consumer homologada para retirada e delivery.
- Confirmado uso real do header `xapikey` pelo Consumer; backend mantém compatibilidade com `Authorization: Bearer`.
- Confirmado callback de status operacional em `POST /orders/status`, com `OrderId` no corpo; rota com UUID no caminho permanece compatível.
- Adicionada rota de compatibilidade `POST /orders/details`.
- Consulta `GET /orders/{order_id}` passou a marcar `PLC` pendente como entregue no runtime homologado.
- Normalização de status ajustada para aceitar formatos como `ReadyToPickup`, `ReadyForPickup` e `OutForDelivery`.
- Payload DELIVERY homologado com `deliveredBy: "Partner"`, `formattedAddress`, `coordinates` e `delivery.observations`.
- Catálogo rico importado do `.prodcon` real do Consumer: 212 produtos, 40 complementos, 129 grupos/produtos com complementos e 1849 vínculos grupo-item.
- AMERICANO homologado com complementos reais Bacon e Queijo, preservando códigos PDV no pedido enviado ao Consumer.
- OpenAI configurada na VPS; Olívia validada no runtime real com 13 tools, catálogo, complementos, carrinho e checkout.
- Proteção de checkout confirmada: `checkout_cart` não é chamado antes da confirmação explícita do cliente.
- TAKEOUT criado pela Olívia e homologado em `PLACED → CONFIRMED → READY → CONCLUDED`.
- DELIVERY criado pela Olívia e homologado em `PLACED → CONFIRMED → READY → DISPATCHED → CONCLUDED`, incluindo endereço e taxa de entrega.
- Pedidos novos `000019` e `000020` processados simultaneamente; callbacks intercalados mantiveram os UUIDs corretos, sem mistura entre pedidos.
- Adicionada proteção contra regressão de status e reabertura de estados terminais.
- Hotfixes Consumer que estavam apenas na VPS foram consolidados no GitHub e sincronizados novamente com a produção.
- Removido log de payload bruto dos callbacks de status.
- Access log do Caddy passou a remover `Xapikey` antes da gravação; teste controlado confirmou ausência do token em novos logs.
- Credencial Consumer rotacionada após exposição histórica em logs. Foi identificado cache da chave antiga no componente de alteração manual de status do Consumer; após reinício completo do Consumer, polling e callbacks passaram a responder `200 OK` com a nova chave.
- Diagnósticos temporários de autenticação/hash e de status foram removidos do código em 2026-08-12.
- Cópia temporária da nova credencial no Windows foi removida e a área de transferência foi limpa.
- WhatsApp permanece implementado no código, porém ainda não configurado para o canal real da Old Burguer 87.
- Documentação atualizada para separar estado implementado, configurado e homologado.

## 0.3.4

- Alinhado o roadmap com o histórico real das versões implementadas.
- Registradas formalmente as decisões de VPS, domínio, Cloudflare, Caddy e URL pública canônica.
- Registrada a prioridade absoluta de homologar o primeiro pedido no Consumer antes de expandir escopo.
- Consolidado `configure_consumer_partner` como provisionador oficial.
- Removidas referências documentais ao script obsoleto `configure_consumer_integration`.
- Substituído `api.seudominio.com` por `smartfoodia.com.br` na documentação oficial do piloto.
- Atualizado `.env.example` para a base pública oficial da homologação.
- Nenhuma regra funcional do Core ou contrato de integração foi alterada nesta versão.

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
