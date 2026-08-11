# Roadmap Oficial

## Histórico entregue

- **v0.0.1 — Fundação:** FastAPI, Docker, PostgreSQL, configurações e health check.
- **v0.0.2 — Banco e catálogo inicial:** SQLAlchemy, Alembic, empresas, lojas, categorias, produtos e API inicial.
- **v0.0.3 — Importador e complementos:** importador Consumer, complementos, grupos, compatibilidade e validação de códigos PDV.
- **v0.0.4 — Clientes e carrinho:** clientes, endereços, carrinhos, itens, opções e cálculo.
- **v0.0.5 — Pedidos:** checkout, pagamento, entrega, pedidos, eventos e proteção contra duplicidade.
- **v0.0.6 — Consumer Adapter:** polling, detalhes, eventos, status, autenticação e testes de contrato.
- **v0.0.7 — Olívia:** ferramentas, catálogo, carrinho, checkout e escalação humana.
- **v0.0.8 — WhatsApp:** webhook, envio, sessões, mídia básica e retomada de conversa.
- **v0.0.9 — Piloto técnico inicial:** consolidação da fundação do MVP.
- **v0.1.x — Conversação e operação:** evolução de conversas, provedor OpenAI, gateway WhatsApp, filas, worker, takeover humano, operações de suporte e dashboard operacional.
- **v0.2.x — Console e web:** dashboard web e console de conversas/operação.
- **v0.3.0–v0.3.2 — Consumer hardening:** revisão e endurecimento do contrato da API Parceiro, remoção de dependências fixas de loja e preparação para homologação real.
- **v0.3.3 — Consumer Homologation & Public HTTPS:** Caddy, HTTPS automático, diagnóstico protegido, verificador externo e roteiro de homologação.
- **v0.3.4 — Documentation & Governance Alignment:** documentação e decisões alinhadas ao estado então conhecido do projeto.
- **Homologação operacional de 2026-08-11:** retirada e delivery validados de ponta a ponta no Consumer, com callbacks de status e payload DELIVERY ajustado em produção.

## Gates atuais até a V1

### Gate A — DNS público — CONCLUÍDO

- `smartfoodia.com.br` resolve para a VPS pública.

### Gate B — HTTPS público — CONCLUÍDO

- Caddy ativo;
- certificado TLS válido para `smartfoodia.com.br`.

### Gate C — Diagnóstico da API Parceiro — CONCLUÍDO

- `/ready` operacional;
- autenticação da integração validada;
- merchant configurado;
- polling e URLs operacionais funcionando externamente.

### Gate D — Configuração no Consumer — CONCLUÍDO

- integração cadastrada;
- Consumer realizando polling e consultando pedidos;
- autenticação real observada via `xapikey`.

### Gate E — Primeiro pedido controlado — CONCLUÍDO

- pedido válido publicado;
- `PLACED / PLC` disponibilizado;
- Consumer consultou detalhes;
- pedido apareceu corretamente na fila;
- fluxo sem duplicidade observado nos testes controlados.

### Gate F — Retorno de status — CONCLUÍDO PARA RETIRADA E DELIVERY

Homologado em 2026-08-11:

#### Retirada
- `Confirmed`;
- `ReadyToPickup`;
- `Concluded`.

#### Delivery
- `Confirmed`;
- despacho / `Em Rota`;
- `Concluded`.

Os estados foram persistidos no SmartFoodIA com respostas HTTP `200 OK`.

### Gate G — Homologação ampliada — EM ANDAMENTO

Ainda devem ser cobertos de forma controlada os demais cenários aprovados:

- cancelamento;
- adicionais e observações reais;
- PIX pendente;
- cartão crédito/débito;
- dinheiro e troco;
- indisponibilidade;
- alteração antes da confirmação;
- idempotência e repetição de polling;
- retomada após falha;
- pedido iniciado pela Olívia usando o fluxo real do cliente.

Também é necessário consolidar no GitHub os hotfixes que estão em produção no adaptador Consumer antes de qualquer novo deploy.

### Gate H — Produção assistida — PENDENTE

Antes do piloto produtivo:

- configurar OpenAI na VPS;
- configurar a conta WhatsApp da loja;
- validar o fluxo WhatsApp → Olívia → Core → Consumer → status → WhatsApp;
- corrigir a exposição de `xapikey` nos access logs do Caddy;
- backup e restauração testados;
- monitoramento e observabilidade;
- segurança final da VPS;
- procedimentos operacionais mínimos.

## v1.0.0 — Produção

Critério: Old Burguer 87 operando de forma estável com pedido real via WhatsApp/Olívia entrando no Consumer, retorno de status chegando ao SmartFoodIA e ao cliente, proteção contra duplicidade, segurança de logs, observabilidade e procedimentos operacionais mínimos.

## Depois da V1

Painel mais amplo, fidelidade, campanhas, pagamentos avançados, novos ERPs e eventual ERP próprio permanecem evolução futura. A arquitetura deve continuar permitindo novos adapters sem acoplar o Core ao Consumer.

Consulte também `docs/PRODUCTION_RUNTIME.md` para o estado efetivamente auditado da VPS.
