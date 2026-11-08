# Gateway do WhatsApp Cloud API

<!-- SMARTFOODIA-WHATSAPP-2026-09-07:START -->
## Atualização do gateway — 2026-09-07

O gateway possui tratamento determinístico para algumas intenções em que uma
chamada ao modelo de IA não é necessária.

### Solicitação ampla de cardápio

Pedidos amplos de cardápio podem ser classificados pelo gateway como `MENU` ou
`PDF`.

Quando existe PDF oficial utilizável:

1. o gateway executa `send_menu_pdf`;
2. o documento é enviado pelo WhatsApp;
3. é enviada resposta curta de confirmação;
4. a mensagem não precisa seguir para uma chamada GPT.

Se o PDF não estiver disponível ou não estiver sincronizado com o catálogo
ativo, o tratamento determinístico é abandonado e a mesma intenção segue para
a Olívia usar o catálogo como fallback.

Solicitação explícita por cardápio online/link/site continua sendo tratada
separadamente e respeita exclusivamente a URL oficial cadastrada.

### PIX Copia e Cola

Depois da execução da Olívia, o gateway verifica se ocorreu um
`checkout_cart` PIX bem-sucedido no ciclo atual.

Quando aplicável:

1. recupera total e `display_id` do checkout;
2. consulta as regras comerciais PIX;
3. gera o BR Code deterministicamente;
4. registra mensagem com tipo `PIX_COPY_PASTE`;
5. marca `deterministic = true`;
6. marca `openai_used = false`;
7. envia o código como mensagem separada ao cliente.

Esse fluxo evita delegar à IA cálculo financeiro ou montagem do payload PIX.
<!-- SMARTFOODIA-WHATSAPP-2026-09-07:END -->

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

<!-- SMARTFOODIA-WHATSAPP-2026-10-13:START -->
## Estado de produção — 2026-10-13

A informação histórica acima referente a 2026-08-11 não representa mais o estado atual do ambiente.

O WhatsApp Cloud foi posteriormente configurado e homologado em produção para a Old Burguer 87.

O fluxo operacional ativo inclui:

`WhatsApp → Olívia → Core → Consumer → status → WhatsApp`

O takeover humano também foi homologado.

### Controle de WhatsApp administrativo por membro da equipe

Membros da equipe possuem a configuração `notify_whatsapp`.

Quando `notify_whatsapp=False`:

- o membro não deve receber notificações administrativas selecionadas pelo sistema;
- não deve receber encaminhamento de conversa/mídia como atendente;
- mensagens enviadas por esse número ao gateway continuam sendo reconhecidas como provenientes da equipe;
- essas mensagens são marcadas como `IGNORED`;
- elas não são encaminhadas para a Olívia como mensagens de cliente.

Em 13/10/2026 o WhatsApp administrativo da atendente `5597984053985` foi desativado dessa forma.

Essa configuração não desativa o canal dos clientes e não interfere no fechamento de turno disponível no painel web.

Detalhes operacionais e rollback estão documentados em:

`docs/SHIFT_CLOSING_AND_ADMIN_WHATSAPP_2026-10-13.md`
<!-- SMARTFOODIA-WHATSAPP-2026-10-13:END -->
