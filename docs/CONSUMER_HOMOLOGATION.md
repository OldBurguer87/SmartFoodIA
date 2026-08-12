# Homologação da API Parceiro Consumer

## Estado atual

Homologação operacional atualizada em **2026-08-12**.

Base pública oficial:

```text
https://smartfoodia.com.br
```

DNS, HTTPS, autenticação, polling, consulta de detalhes, pedidos TAKEOUT, pedidos DELIVERY, complementos, checkout via Olívia e retorno completo de status já foram validados em produção controlada.

## Pré-requisitos cumpridos

- DNS público apontando para a VPS;
- Caddy ativo;
- certificado TLS válido;
- assinatura Premium do Consumer;
- integração ativa para a Old Burguer 87;
- merchant configurado;
- produtos e complementos com códigos PDV válidos;
- token Consumer configurado e rotacionado;
- OpenAI configurada para a Olívia.

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

Status — formato observado em produção:
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/status

Status — compatibilidade:
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/status

Detalhes — compatibilidade runtime:
POST https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/details
```

## Homologação de retirada

Pedido novo usado no teste simultâneo:

```text
000019
TAKEOUT
Americano + Bacon + Queijo
R$ 12,00
```

Fluxo validado:

```text
PLACED / PLC
→ Confirmed
→ ReadyToPickup
→ Concluded
```

Persistência final:

```text
PLC | PLACED          | DELIVERED
CFM | CONFIRMED       | DELIVERED
RTP | READY_TO_PICKUP | DELIVERED
CON | CONCLUDED       | DELIVERED
```

Status final: `CONCLUDED`.

## Homologação de delivery

Pedido novo usado no teste simultâneo:

```text
000020
DELIVERY
Americano + Bacon + Queijo
Subtotal R$ 12,00
Taxa de entrega R$ 3,00
Total R$ 15,00
Rua 14, 204, União, Coari-AM
Referência: Cond. Fechado
```

Fluxo validado:

```text
PLACED / PLC
→ Confirmed
→ ReadyToPickup
→ Dispatched
→ Concluded
```

Persistência final:

```text
PLC | PLACED          | DELIVERED
CFM | CONFIRMED       | DELIVERED
RTP | READY_TO_PICKUP | DELIVERED
DSP | DISPATCHED      | DELIVERED
CON | CONCLUDED       | DELIVERED
```

Status final: `CONCLUDED`.

## Teste simultâneo / concorrência

Os pedidos `000019` e `000020` foram processados com callbacks intercalados.

Cada retorno manteve o UUID correto do respectivo pedido. Não foi observada mistura de `order_id`, status ou eventos entre os dois pedidos.

Conclusão: o comportamento estranho observado em pedidos antigos durante a rotação de credencial não se reproduziu em pedidos novos criados do zero.

## Complementos reais

O catálogo rico foi importado do `.prodcon` do Consumer.

Importação auditada:

```text
Produtos no arquivo: 212
Detalhes: 264
Complementos: 40
Vínculos: 1849
Grupos criados: 129
Produtos com complementos: 129
Vínculos grupo-item: 1849
Produtos locais não encontrados: 0
Detalhes de complemento não encontrados: 0
```

O AMERICANO foi testado com Bacon e Queijo, e os códigos PDV dos complementos chegaram corretamente ao Consumer.

## Checkout pela Olívia

Foram homologados:

- montagem do carrinho pela Olívia;
- bloqueio de `checkout_cart` antes da confirmação explícita;
- checkout após confirmação explícita;
- TAKEOUT com pagamento débito;
- DELIVERY com endereço e taxa de entrega;
- envio ao Consumer;
- retorno de status até conclusão.

## Normalização de status

A produção trata diferenças de maiúsculas, hífens, espaços, underscores e nomes compactos.

Exemplos:

```text
ReadyToPickup -> READY
ReadyForPickup -> READY
Dispatched -> DISPATCHED
OutForDelivery -> DISPATCHED
Concluded -> CONCLUDED
Delivered -> CONCLUDED
```

## Proteção contra regressão

Callbacks tardios não podem mais reabrir pedidos ou reduzir o estágio operacional.

Exemplos bloqueados:

```text
CONCLUDED -> READY
DISPATCHED -> READY
READY -> CONFIRMED
```

## Segurança da credencial

A credencial Consumer foi rotacionada durante a homologação.

Após a troca foi necessário reiniciar completamente o Consumer para que o componente de alteração manual de status deixasse de usar uma chave antiga mantida em memória.

Depois do reinício:

- polling: `200 OK`;
- `Confirmed`: `200 OK`;
- `ReadyToPickup`: `200 OK`;
- `Dispatched`: `200 OK`;
- `Concluded`: `200 OK`.

Os diagnósticos temporários de hash/token usados para localizar o problema foram removidos do código em 2026-08-12.

## Situação dos gates

- DNS: aprovado;
- HTTPS: aprovado;
- configuração Consumer: aprovada;
- catálogo e complementos reais: aprovados;
- checkout Olívia: aprovado;
- retirada completa: aprovada;
- delivery completo: aprovado;
- callbacks simultâneos: aprovados;
- retorno de status: aprovado;
- WhatsApp real: pendente.

## Pendências antes do piloto produtivo

- configurar conta WhatsApp Cloud;
- configurar webhook;
- validar WhatsApp → Olívia → Consumer → status → WhatsApp;
- testar cancelamento;
- testar PIX, crédito, dinheiro e troco em cenários próprios;
- validar idempotência e retomada de falhas em testes dedicados;
- backup, monitoramento e procedimentos operacionais.

Consulte também `docs/PRODUCTION_RUNTIME.md`.
