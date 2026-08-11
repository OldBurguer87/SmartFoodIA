# Homologação da API Parceiro Consumer

## Estado atual

Homologação operacional atualizada em **2026-08-11**.

Base pública oficial:

```text
https://smartfoodia.com.br
```

DNS, HTTPS, integração Consumer, pedidos de retirada, pedidos delivery e retorno de status já foram validados em produção controlada.

## Pré-requisitos já cumpridos

- DNS público apontando para a VPS;
- Caddy ativo;
- certificado TLS válido;
- assinatura Premium do Consumer;
- integração ativa para a loja;
- merchant configurado;
- produtos com `externalCode` válido;
- token Consumer configurado.

## Serviços públicos

O Caddy publica atualmente:

```text
/api/*
/live
/ready
```

As rotas internas `/health` e `/version` existem na FastAPI, mas não estão publicadas diretamente no domínio raiz; externamente retornam 404 por serem encaminhadas ao frontend.

## Configuração da loja

Provisionador oficial:

```bash
docker compose exec api python -m app.scripts.configure_consumer_partner \
  --store-slug old-burguer-87 \
  --merchant-id ID_DO_CONSUMER \
  --merchant-name "Old Burguer 87" \
  --base-url https://smartfoodia.com.br
```

`configure_consumer_integration` é legado.

## Autenticação

O backend aceita:

```text
Authorization: Bearer TOKEN
```

ou:

```text
xapikey: TOKEN
```

Na integração real homologada, o Consumer utilizou `xapikey`.

## URLs validadas

```text
Polling:
GET https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/events

Detalhes:
GET https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}

Evento ODR:
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/events

Status — formato usado pelo Consumer homologado:
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/status

Status — compatibilidade:
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/status

Detalhes — compatibilidade runtime:
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/details
```

## Homologação de retirada

Fluxo validado:

```text
PLACED / PLC
→ Confirmed
→ ReadyToPickup
→ Concluded
```

O SmartFoodIA persistiu corretamente:

```text
CONFIRMED
READY
CONCLUDED
```

com eventos correspondentes.

## Homologação de delivery

O primeiro payload delivery testado era aceito pela nossa API, mas não entrava no Consumer. O pedido passou a entrar após alinhar o bloco de entrega ao baseline homologado, incluindo:

- `deliveredBy: "Partner"`;
- `formattedAddress`;
- `coordinates.latitude` e `coordinates.longitude`;
- `delivery.observations`.

Fluxo validado:

```text
PLACED / PLC
→ Confirmed
→ Em Rota
→ Concluded
```

O SmartFoodIA persistiu corretamente:

```text
CONFIRMED
DISPATCHED
CONCLUDED
```

## Normalização de status

A produção trata diferenças de formato recebidas do Consumer. Exemplos:

```text
ReadyToPickup -> READY
ReadyForPickup -> READY
OutForDelivery -> DISPATCHED
Concluded -> CONCLUDED
Delivered -> CONCLUDED
```

## Situação dos gates

- DNS: aprovado;
- HTTPS: aprovado;
- configuração Consumer: aprovada;
- primeiro pedido: aprovado;
- retorno de status: aprovado para retirada e delivery;
- homologação ampliada: em andamento;
- produção assistida: pendente.

## Pendências antes do piloto produtivo

- consolidar no GitHub os hotfixes funcionais atualmente executados na VPS;
- configurar OpenAI na VPS;
- configurar conta WhatsApp e webhook;
- validar pedido real WhatsApp → Olívia → Consumer → WhatsApp;
- testar cancelamento e meios de pagamento restantes;
- validar idempotência e retomada de falhas;
- impedir que `xapikey` seja exposto no access log do Caddy;
- backup, monitoramento e procedimentos operacionais.

## Regra para novos testes

Não reduzir o payload DELIVERY homologado nem trocar as rotas operacionais sem teste controlado. O comportamento observado em produção prevalece sobre exemplos antigos de documentação interna.

Consulte também `docs/PRODUCTION_RUNTIME.md`.
