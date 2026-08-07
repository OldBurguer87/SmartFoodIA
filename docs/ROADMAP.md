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
- **v0.3.4 — Documentation & Governance Alignment:** documentação e decisões alinhadas ao estado real do projeto, sem mudança funcional do Core.

## Gates atuais até a V1

### Gate A — DNS público

- Cloudflare reconhecer os nameservers do `smartfoodia.com.br`.
- Registros DNS apontarem corretamente para a VPS.

**Saída:** domínio resolvendo publicamente para o servidor correto.

### Gate B — HTTPS público

- Subir Caddy com a configuração de produção.
- Emitir certificado TLS válido para `smartfoodia.com.br`.

**Saída:** `https://smartfoodia.com.br` acessível externamente.

### Gate C — Diagnóstico da API Parceiro

- `health` operacional.
- autenticação por token validada;
- merchant configurado;
- polling e URLs finais funcionando externamente.

**Saída:** API pronta para cadastro no Consumer.

### Gate D — Configuração no Consumer

- cadastrar token e as quatro URLs da API Parceiro;
- ativar a Fila de Pedidos Online.

**Saída:** Consumer consultando a API do SmartFoodIA.

### Gate E — Primeiro pedido controlado

- criar pedido válido;
- exigir confirmação explícita;
- gerar `PLACED / PLC`;
- Consumer consultar detalhes;
- pedido aparecer corretamente na fila do Consumer;
- nenhuma duplicidade.

**Saída:** primeiro pedido integrado de ponta a ponta até a fila do Consumer.

### Gate F — Retorno de status

- validar confirmação;
- cancelamento;
- pronto para retirada;
- saiu para entrega;
- conclusão;
- refletir estados no SmartFoodIA.

**Saída:** ciclo bidirecional Consumer ↔ SmartFoodIA homologado.

### Gate G — Homologação ampliada

Testar os cenários aprovados de retirada, delivery, adicionais, observações, PIX pendente, cartões, dinheiro/troco, indisponibilidade, alterações antes da confirmação, idempotência, repetição de polling e retomada após falha.

**Saída:** matriz mínima de homologação aprovada.

### Gate H — Produção assistida

- backup;
- monitoramento;
- segurança final da VPS;
- observabilidade;
- operação assistida com a Old Burguer 87.

**Saída:** piloto produtivo estável.

## v1.0.0 — Produção

Critério: primeiro piloto operando de forma estável com pedido via SmartFoodIA entrando no Consumer, retorno de status funcionando, proteção contra duplicidade, observabilidade e procedimentos operacionais mínimos.

## Depois da V1

Painel mais amplo, fidelidade, campanhas, pagamentos avançados, novos ERPs e eventual ERP próprio permanecem evolução futura. A arquitetura deve continuar permitindo novos adapters sem acoplar o Core ao Consumer.
