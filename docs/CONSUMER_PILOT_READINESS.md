# Preparação do piloto Consumer

## Objetivo

Fechar o ciclo aprovado:

```text
WhatsApp → Olívia → pedido confirmado → Consumer → atualização de status → WhatsApp
```

## Estado em 2026-08-11

A integração Consumer já foi homologada para retirada e delivery. O ciclo completo ainda não está pronto para piloto real porque OpenAI e WhatsApp não estavam configurados na VPS auditada.

### Já validado

- DNS e HTTPS;
- polling Consumer;
- consulta de detalhes;
- pedido de retirada entrando na fila;
- pedido delivery entrando na fila;
- `Confirmed`;
- `ReadyToPickup`;
- despacho / Em Rota;
- `Concluded`;
- persistência de status no SmartFoodIA.

### Ainda pendente

- `OPENAI_API_KEY` em produção;
- conta WhatsApp da loja;
- token/app secret WhatsApp;
- webhook real;
- teste do ciclo completo com cliente;
- cancelamento e meios de pagamento restantes;
- segurança dos logs do Caddy;
- consolidação dos hotfixes Consumer no GitHub.

## Configuração da loja Consumer

```bash
docker compose exec api python -m app.scripts.configure_consumer_partner \
  --store-slug old-burguer-87 \
  --merchant-id ID_DO_ESTABELECIMENTO_NO_CONSUMER \
  --merchant-name "Old Burguer 87" \
  --base-url https://smartfoodia.com.br
```

## Atualizações ao cliente

O código possui notifier para os estados internos:

- `CONFIRMED`;
- `READY`;
- `DISPATCHED`;
- `CONCLUDED`;
- `CANCELLED`.

Essas mensagens só podem chegar ao cliente quando existir uma conta WhatsApp configurada para a loja. Na auditoria de 2026-08-11 não havia nenhuma conta em `channel_accounts`.

## Segurança

- somente o hash do token Consumer fica persistido;
- o backend aceita `Authorization: Bearer` e `xapikey`;
- cada integração pertence a uma loja;
- logs não devem expor tokens;
- foi identificada exposição do header `xapikey` no access log do Caddy durante a homologação, devendo ser corrigida antes da produção assistida.

Consulte `docs/PRODUCTION_RUNTIME.md` para o estado auditado.
