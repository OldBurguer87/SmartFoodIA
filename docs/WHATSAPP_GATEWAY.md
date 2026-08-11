# Gateway do WhatsApp Cloud API

## Arquitetura

O WhatsApp é um adaptador de canal. Ele não acessa catálogo, carrinho ou pedidos diretamente.

```text
Meta Webhook → Channel Gateway → Conversation → OliviaOrchestrator → Tools → Core
```

A Cloud API usa a Graph API para envio e webhooks para recebimento de mensagens e eventos.

## Estado do código

O gateway, filas, worker, persistência de eventos, takeover humano e envio de mensagens já estão implementados.

## Estado da produção auditada em 2026-08-11

```text
WHATSAPP_TOKEN_CONFIGURED=False
WHATSAPP_APP_SECRET_CONFIGURED=False
channel_accounts=0
```

O worker estava em execução, mas nenhuma conta WhatsApp da loja estava configurada. Portanto, o canal ainda não estava ativo para tráfego real.

## Configuração esperada

No `.env`:

```text
WHATSAPP_ACCESS_TOKEN=token_da_meta
WHATSAPP_APP_SECRET=app_secret_da_meta
WHATSAPP_GRAPH_API_VERSION=v23.0
WHATSAPP_TIMEOUT_SECONDS=30
```

Depois das migrations:

```bash
docker compose exec api python -m app.scripts.configure_whatsapp_channel \
  --store-slug old-burguer-87 \
  --phone-number-id ID_DO_NUMERO \
  --display-phone-number 5597XXXXXXXXX
```

## Webhook

Callback:

```text
https://smartfoodia.com.br/api/v1/channels/whatsapp/webhook
```

O endpoint atende:

- `GET`: verificação;
- `POST`: mensagens e atualizações de status.

## Segurança e confiabilidade

- validação de `X-Hub-Signature-256` quando `WHATSAPP_APP_SECRET` está configurado;
- idempotência pelo ID externo da mensagem/evento;
- eventos persistidos antes do processamento;
- mensagens de saída persistidas com status e tentativas;
- retentativas e estado `DEAD` após limite;
- tipos não suportados podem ser marcados como `IGNORED`.

## Próximo passo operacional

Configurar a conta real da Old Burguer 87 e validar o ciclo completo:

```text
WhatsApp → Olívia → Core → Consumer → status → WhatsApp
```

O Consumer já foi homologado separadamente. A etapa pendente é ativar e homologar o canal WhatsApp em produção.

Consulte `docs/PRODUCTION_RUNTIME.md`.
