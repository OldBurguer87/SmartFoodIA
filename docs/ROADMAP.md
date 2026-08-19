# Roadmap Oficial

Atualizado em **2026-08-19** após a virada para produção assistida da Old Burguer 87.

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
- **v0.1.x — Conversação e operação:** conversas, OpenAI, gateway WhatsApp, filas, worker, takeover humano, suporte e dashboard operacional.
- **v0.2.x — Console e web:** dashboard web e console operacional.
- **v0.3.0–v0.3.2 — Consumer hardening:** revisão e endurecimento da API Parceiro.
- **v0.3.3 — Consumer Homologation & Public HTTPS:** Caddy, HTTPS, diagnóstico e roteiro de homologação.
- **v0.3.4 — Documentation & Governance Alignment:** documentação alinhada ao estado conhecido à época.
- **Homologação 2026-08-11/12:** Consumer validado de ponta a ponta para TAKEOUT e DELIVERY; Olívia ativada; catálogo real com complementos; checkout e ciclo completo de status aprovados.
- **Hardening 2026-08-12:** credencial Consumer rotacionada, callbacks estabilizados, proteção contra regressão de status e concorrência entre pedidos validada.
- **Homologação WhatsApp 2026-08-18/19:** número oficial Cloud API ativado; webhook validado; Olívia respondendo pelo canal real; atendimento humano, comandos operacionais, mídia e retomada homologados.
- **Hardening operacional commit `832f93e` — 2026-08-19:** escalonamento gerencial, `LOCALIZAR PEDIDO`, mídia/localização no atendimento humano, cadeia pós-rejeição PIX, alertas críticos e trava de integração Consumer para PIX não confirmado.
- **Virada para produção assistida — 2026-08-19:** 231 testes aprovados, backups validados, rollback preparado, base operacional de testes zerada e imagens `deploy-832f93e` colocadas em produção.

## Gates até a V1

### Gate A — DNS público — CONCLUÍDO

- `smartfoodia.com.br` resolve para a VPS pública.

### Gate B — HTTPS público — CONCLUÍDO

- Caddy ativo;
- certificado TLS válido.

### Gate C — Diagnóstico da API Parceiro — CONCLUÍDO

- `/ready` operacional;
- autenticação validada;
- merchant configurado;
- polling e URLs operacionais funcionando externamente.

### Gate D — Configuração no Consumer — CONCLUÍDO

- integração ativa;
- polling real;
- autenticação via `xapikey` homologada;
- callbacks de status funcionando;
- credencial rotacionada e estabilizada.

### Gate E — Pedido controlado — CONCLUÍDO

- `PLACED / PLC` disponibilizado;
- Consumer consulta detalhes;
- TAKEOUT e DELIVERY entram corretamente;
- produtos e complementos reais validados por códigos PDV.

### Gate F — Retorno de status — CONCLUÍDO

#### Retirada

- `Confirmed`;
- `ReadyToPickup`;
- `Concluded`.

#### Delivery

- `Confirmed`;
- `ReadyToPickup`;
- `Dispatched`;
- `Concluded`.

Proteção contra regressão e mistura entre pedidos simultâneos homologada.

### Gate G — Homologação ampliada — CONCLUÍDO PARA ENTRADA EM PRODUÇÃO ASSISTIDA

Coberto:

- OpenAI/Olívia operacional;
- catálogo e complementos reais;
- carrinho e confirmação explícita;
- TAKEOUT e DELIVERY;
- taxa de entrega;
- débito e cenários PIX;
- retorno completo de status;
- callbacks simultâneos;
- proteção contra regressão;
- agendamento com `release_at`;
- comprovante PIX com revisão/antifraude;
- cadeia pós-rejeição PIX;
- atendimento humano e retomada automática;
- localização e imagem no atendimento humano;
- `LOCALIZAR PEDIDO`;
- alertas gerenciais e operacionais;
- proteção para não publicar pedido PIX ao Consumer antes da confirmação do pagamento.

Ainda devem ser aprofundados durante produção assistida:

- cancelamento em cenários reais;
- cartão de crédito;
- dinheiro e troco;
- indisponibilidade de serviços externos;
- alteração de pedido antes da confirmação;
- retomada após falha real;
- comportamento em volume e concorrência de clientes reais.

### Gate H — WhatsApp oficial — CONCLUÍDO

- número oficial Cloud API ativo;
- webhook público validado;
- conversa real WhatsApp → Olívia homologada;
- envio de texto e imagem validado;
- atendimento humano validado;
- status e comandos operacionais validados;
- Consumer e WhatsApp coexistindo no runtime de produção.

### Gate I — Produção assistida — ATIVO

Iniciada em **2026-08-19**.

Condições de entrada cumpridas:

- commit `832f93e` em produção;
- **231 testes** de backend aprovados;
- API/worker/web passaram em smoke tests;
- `/ready` externo retornando `HTTP 200` com banco disponível;
- Alembic `0017 (head)`;
- backup de desenvolvimento validado;
- backup `produção-zero` validado;
- imagens de rollback preservadas;
- logs iniciais sem erro;
- Consumer ativo e atualizando polling.

Pendência externa não bloqueante:

- template Meta `alerta_operacional_gerente` permanece **Em análise**. Enquanto não for aprovado, alertas proativos ao gerente fora da janela do WhatsApp podem não ser enviados. O fluxo principal não depende dele.

## Próximos marcos

### Marco 1 — Estabilização dos primeiros pedidos reais

- acompanhar primeiras jornadas reais completas;
- observar erros de OpenAI, WhatsApp, Consumer e filas;
- conferir pedidos PIX reais antes da exposição ao Consumer;
- validar status e mensagens ao cliente;
- registrar incidentes sem alterar o Core por exceções isoladas.

### Marco 2 — Fechamento do template gerencial

- aguardar decisão da Meta;
- se aprovado, executar teste controlado fora da janela de 24h;
- se rejeitado, ajustar template sem bloquear operação principal.

### Marco 3 — V1 estável

Critério para declarar **v1.0.0**:

- operação real estável por período de observação suficiente;
- pedidos reais WhatsApp → Olívia → Consumer completos;
- retorno de status consistente;
- PIX não confirmado nunca exposto ao Consumer;
- atendimento humano e retomada confiáveis;
- backup e rollback validados;
- logs e alertas sem incidentes críticos recorrentes;
- procedimentos operacionais documentados.

## Depois da V1

Painel ampliado, fidelidade, campanhas, pagamentos avançados, novos ERPs e eventual ERP próprio permanecem evolução futura. A arquitetura deve continuar permitindo adapters sem acoplar o Core ao Consumer.

Consulte também `docs/PRODUCTION_RUNTIME.md`.
