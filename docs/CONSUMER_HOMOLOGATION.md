# Homologação da API Parceiro Consumer

## Estado atual

Homologação operacional atualizada em **2026-08-19**.

Base pública oficial:

```text
https://smartfoodia.com.br
```

DNS, HTTPS, autenticação, polling, consulta de detalhes, TAKEOUT, DELIVERY, complementos, checkout via Olívia, retorno de status e canal WhatsApp oficial já foram validados em produção controlada.

A Old Burguer 87 entrou em **produção assistida** no commit `832f93e` em 2026-08-19.

## Pré-requisitos cumpridos

- DNS público apontando para a VPS;
- Caddy ativo;
- certificado TLS válido;
- assinatura Premium do Consumer;
- integração ativa para a Old Burguer 87;
- merchant configurado;
- produtos e complementos com códigos PDV válidos;
- token Consumer configurado e rotacionado;
- OpenAI configurada para a Olívia;
- WhatsApp Cloud oficial configurado;
- webhook público ativo;
- worker, API e frontend ativos;
- Alembic `0017 (head)`.

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

## Retirada homologada

Fluxo validado:

```text
PLACED / PLC
→ Confirmed
→ ReadyToPickup
→ Concluded
```

Status final: `CONCLUDED`.

## Delivery homologado

Fluxo validado:

```text
PLACED / PLC
→ Confirmed
→ ReadyToPickup
→ Dispatched
→ Concluded
```

Status final: `CONCLUDED`.

## Concorrência

Pedidos simultâneos foram processados com callbacks intercalados sem mistura de UUID, status ou eventos.

A proteção contra regressão impede callbacks tardios de reduzir o estágio operacional ou reabrir estados terminais.

## Complementos reais

O catálogo rico foi importado do `.prodcon` do Consumer e produtos com complementos reais foram validados por códigos PDV no pedido enviado ao Consumer.

## Checkout pela Olívia

Homologado:

- montagem de carrinho;
- confirmação explícita obrigatória;
- TAKEOUT;
- DELIVERY;
- endereço e taxa de entrega;
- envio ao Consumer;
- retorno de status até conclusão.

## PIX e liberação ao Consumer

O hardening de 2026-08-19 adicionou uma regra obrigatória:

```text
PIX + DELIVERY/TAKEOUT
```

só é exposto ao Consumer quando o comprovante estiver em:

```text
AUTO_CONFIRMED
ou
HUMAN_CONFIRMED
```

Comprovantes `NEEDS_REVIEW` ou `HUMAN_REJECTED` não liberam o pedido.

Pedidos agendados precisam também ter atingido `release_at`.

Essa regra foi validada por testes de polling, detalhes e proteção de acesso direto ao adapter.

## WhatsApp oficial

Estado: **homologado e ativo**.

Validado:

- webhook;
- recebimento de texto;
- recebimento de imagem;
- resposta da Olívia;
- atendimento humano;
- comandos de assumir/devolver/resolver/status;
- mídia em conversa humana;
- localização do cliente;
- retomada automática da Olívia.

## Escalonamento gerencial

O commit `832f93e` adicionou:

- gerente separado da fila comum de atendentes;
- alerta após handoff não assumido;
- alerta final de PIX rejeitado;
- alerta de incidente operacional crítico;
- possibilidade de gerente assumir conversa recentemente escalada;
- deduplicação de incidentes do monitor.

O template Meta `alerta_operacional_gerente` permanece **Em análise** em 2026-08-19. Essa pendência não bloqueia o fluxo principal; afeta apenas alertas proativos ao gerente que dependam de iniciar conversa fora da janela permitida pelo WhatsApp.

## Testes de entrada em produção assistida

Antes do deploy de 2026-08-19:

- **231 testes de backend passaram**;
- imagens de API, worker e web passaram em smoke tests;
- `/ready` externo retornou `HTTP 200` com banco disponível;
- backup pré-produção foi validado;
- backup `produção-zero` foi validado;
- imagens anteriores foram preservadas para rollback;
- logs iniciais pós-deploy ficaram limpos.

## Situação dos gates

- DNS: aprovado;
- HTTPS: aprovado;
- Consumer: aprovado;
- catálogo e complementos reais: aprovados;
- checkout Olívia: aprovado;
- retirada: aprovada;
- delivery: aprovada;
- callbacks simultâneos: aprovados;
- retorno de status: aprovado;
- WhatsApp oficial: aprovado;
- PIX release gate: aprovado por testes;
- produção assistida: **ativa**.

## Pendências de estabilização

- acompanhar primeiros pedidos reais;
- aprofundar cenários reais de cancelamento;
- crédito;
- dinheiro/troco;
- indisponibilidade externa;
- recuperação após falha real;
- testar template gerencial quando a Meta concluir a análise.

Consulte também `docs/PRODUCTION_RUNTIME.md`.
