# SmartFoodIA

## Versão atual

`0.1.3 — WhatsApp Channel Gateway`

Esta versão adiciona o primeiro canal real do SmartFoodIA:

- webhook do WhatsApp Cloud API;
- verificação e assinatura;
- idempotência;
- sessões por telefone;
- integração com o orquestrador da Olívia;
- envio de respostas;
- persistência de eventos e mensagens de saída;
- base preparada para retry e fila.

Consulte `docs/WHATSAPP_GATEWAY.md`.


## Fila de canais

Consulte `docs/CHANNEL_QUEUE.md`. O webhook grava rapidamente o evento e o worker processa a Olívia e o envio com retentativas.
