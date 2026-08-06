# Console visual de conversas

A versão 0.2.1 adiciona ao painel:

- lista de conversas da loja;
- filtros por estado;
- histórico de até 200 mensagens;
- takeover humano;
- resposta pela fila do WhatsApp;
- devolução para a Olívia;
- atualização automática da conversa aberta.

Novo endpoint:

```text
GET /api/v1/operations/conversations/{conversation_id}
```
