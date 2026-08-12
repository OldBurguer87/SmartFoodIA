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
- **v0.3.0–v0.3.2 — Consumer hardening:** revisão e endurecimento do contrato da API Parceiro e preparação para homologação real.
- **v0.3.3 — Consumer Homologation & Public HTTPS:** Caddy, HTTPS automático, diagnóstico protegido, verificador externo e roteiro de homologação.
- **v0.3.4 — Documentation & Governance Alignment:** documentação e decisões alinhadas ao estado então conhecido do projeto.
- **Homologação operacional de 2026-08-11/12:** Consumer validado de ponta a ponta para retirada e delivery; OpenAI/Olívia ativada; catálogo real com complementos importado; checkout real validado; ciclo completo de status aprovado.
- **Hardening de 2026-08-12:** credencial Consumer rotacionada e estabilizada após reinício completo do Consumer; proteção contra regressão de status adicionada; diagnósticos temporários removidos; teste simultâneo de dois pedidos aprovado sem mistura de UUIDs.

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
- autenticação real observada via `xapikey`;
- credencial rotacionada e revalidada;
- callbacks de status retornando `200 OK` após reinício completo do Consumer.

### Gate E — Pedido controlado — CONCLUÍDO

- pedido válido publicado;
- `PLACED / PLC` disponibilizado;
- Consumer consultou detalhes;
- pedidos apareceram corretamente na fila;
- TAKEOUT e DELIVERY criados pela Olívia e enviados ao Consumer;
- produtos e complementos reais validados pelos códigos PDV.

### Gate F — Retorno de status — CONCLUÍDO PARA RETIRADA E DELIVERY

#### Retirada

- `Confirmed`;
- `ReadyToPickup`;
- `Concluded`.

#### Delivery

- `Confirmed`;
- `ReadyToPickup`;
- `Dispatched`;
- `Concluded`.

Todos os estados foram persistidos no SmartFoodIA com eventos `DELIVERED`.

Teste simultâneo com `000019` e `000020` confirmou ausência de mistura entre pedidos.

### Gate G — Homologação ampliada — AVANÇADA / EM ANDAMENTO

Já coberto:

- OpenAI/Olívia operacional;
- catálogo real importado;
- complementos reais;
- carrinho;
- confirmação explícita obrigatória;
- checkout TAKEOUT;
- checkout DELIVERY;
- taxa de entrega;
- débito;
- retorno completo de status;
- callbacks simultâneos;
- proteção contra regressão de status.

Ainda devem ser cobertos em testes dedicados:

- cancelamento;
- PIX pendente;
- cartão crédito;
- dinheiro e troco;
- indisponibilidade;
- alteração de pedido antes da confirmação;
- idempotência e repetição de polling;
- retomada após falha;
- notificações automáticas ao cliente pelo canal real.

### Gate H — Produção assistida via WhatsApp — PENDENTE

Próximos passos:

- configurar a conta WhatsApp Cloud da Old Burguer 87;
- configurar e validar webhook público;
- validar conversa real WhatsApp → Olívia;
- validar pedido completo sem comandos manuais;
- validar status Consumer → SmartFoodIA → cliente;
- backup e restauração testados;
- monitoramento e observabilidade;
- segurança final da VPS;
- procedimentos operacionais mínimos.

## v1.0.0 — Produção

Critério: Old Burguer 87 operando de forma estável com pedido real via WhatsApp/Olívia entrando no Consumer, retorno de status chegando ao SmartFoodIA e ao cliente, proteção contra duplicidade/regressão, segurança de logs, observabilidade e procedimentos operacionais mínimos.

## Depois da V1

Painel mais amplo, fidelidade, campanhas, pagamentos avançados, novos ERPs e eventual ERP próprio permanecem evolução futura. A arquitetura deve continuar permitindo novos adapters sem acoplar o Core ao Consumer.

Consulte também `docs/PRODUCTION_RUNTIME.md`.
