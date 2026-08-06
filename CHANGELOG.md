# Changelog

## 0.3.0
- Criada porta neutra `OrderIntegrationAdapter`.
- Consumer isolado em módulo próprio.
- Pedidos confirmados passam a `READY_FOR_INTEGRATION`.
- Implementados polling, detalhes, ODR e atualização de status.
- Adicionada validação obrigatória de códigos PDV.
- Adicionada idempotência de ODR e status.
- Mantida fachada compatível com a API já existente.
- Adicionados testes do adaptador modular.
