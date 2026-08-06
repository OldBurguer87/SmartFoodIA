# Gateway do WhatsApp Cloud API

## Arquitetura

O WhatsApp é um adaptador de canal. Ele não acessa catálogo, carrinho ou pedidos diretamente.

```text
Meta Webhook → Channel Gateway → Conversation → OliviaOrchestrator → Tools → Core
```

A Cloud API usa a Graph API para envio e webhooks para recebimento de mensagens e eventos.

## Configuração local

No `.env`:

```text
WHATSAPP_ACCESS_TOKEN=token_da_meta
WHATSAPP_APP_SECRET=app_secret_da_meta
WHATSAPP_GRAPH_API_VERSION=v23.0
WHATSAPP_TIMEOUT_SECONDS=30
```

Nunca envie esses valores ao GitHub.

Depois das migrations, configure a conta da loja:

```bash
docker compose exec api python -m app.scripts.configure_whatsapp_channel \
  --store-slug old-burguer-87 \
  --phone-number-id ID_DO_NUMERO \
  --display-phone-number 5597XXXXXXXXX
```

O script solicita o verify token e salva somente o hash.

## Webhook

Callback URL:

```text
https://SEU_DOMINIO/api/v1/channels/whatsapp/webhook
```

O mesmo endpoint atende:

- `GET`: verificação do webhook;
- `POST`: mensagens e atualizações de status.

## Segurança e confiabilidade

- validação de `X-Hub-Signature-256` quando `WHATSAPP_APP_SECRET` está configurado;
- idempotência pelo ID externo da mensagem/evento;
- eventos recebidos persistidos antes do processamento;
- mensagens de saída persistidas com status e tentativas;
- falhas ficam registradas para retry futuro;
- tipos ainda não suportados são marcados como `IGNORED`, sem resposta duplicada.

## Escopo desta versão

Processamento automático de mensagens de texto e status. Imagens, áudio, localização e documentos já são reconhecidos pelo gateway, mas ficam marcados para implementação posterior.
