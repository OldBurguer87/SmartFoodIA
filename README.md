# SmartFoodIA

## Versão atual

`0.3.2 — Consumer Contract Hardening`

Esta versão mantém o foco exclusivo no fluxo aprovado:

```text
WhatsApp → Olívia → pedido confirmado → Consumer → status → cliente
```

Principais ajustes:

- validação rígida de `ODR / ORDER_DETAILS_REQUESTED`;
- nome da loja dinâmico nas notificações;
- remoção do configurador Consumer duplicado;
- testes adicionais do contrato e da modularidade.

Consulte `docs/CONSUMER_HARDENING.md`.
