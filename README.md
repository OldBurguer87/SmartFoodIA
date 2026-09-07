# SmartFoodIA

<!-- SMARTFOODIA-STATE-2026-09-07:START -->
## Estado validado — 2026-09-07

O SmartFoodIA permanece em **produção assistida** na Old Burguer 87.

Estado verificado diretamente na VPS `masterdaweb` em 07/09/2026:

- branch operacional: `feature/plataforma-multiempresa`;
- base antes do commit desta consolidação: `510d6c9`;
- a branch local estava 9 commits à frente de `origin/feature/plataforma-multiempresa`;
- PostgreSQL 17 ativo e saudável;
- `smartfoodia-api` ativo e saudável;
- `smartfoodia-worker` ativo;
- `smartfoodia-web` ativo;
- `smartfoodia-caddy` ativo;
- Alembic confirmado em **`0023 (head)`**;
- `https://smartfoodia.com.br/ready` respondeu com aplicação pronta e banco disponível;
- `git diff --cached --check` sem erros;
- sintaxe Python das alterações validada com `py_compile`;
- bateria direcionada: **96 testes aprovados**;
- suíte completa do backend: **375 testes aprovados**.

Alterações funcionais validadas nesta consolidação:

- apresentação ampla do cardápio passa a priorizar o **PDF oficial**;
- solicitações amplas reconhecidas pelo gateway podem receber o PDF sem chamada desnecessária ao modelo de IA;
- pedido explícito por link/site/cardápio online continua priorizando a URL oficial configurada;
- intenção clara de compra de produto específico não dispara PDF automaticamente;
- PDF inexistente, indisponível ou não sincronizado com a versão ativa do catálogo libera fallback para o catálogo;
- correspondência exata de produto previamente validado pode ser reutilizada com segurança, preservando as proteções de ambiguidade;
- após checkout PIX bem-sucedido, o SmartFoodIA pode gerar e enviar **PIX Copia e Cola deterministicamente**, com valor exato do pedido e TXID associado ao pedido;
- a Olívia não gera nem calcula o BR Code PIX: essa responsabilidade permanece fora da IA.
<!-- SMARTFOODIA-STATE-2026-09-07:END -->

## Estado atual do projeto

Snapshot operacional consolidado até **2026-09-07**.

A Old Burguer 87 iniciou a operação produtiva assistida do SmartFoodIA em `https://smartfoodia.com.br` usando o commit de aplicação **`832f93e`** da branch `feature/plataforma-multiempresa`.

Antes da virada foram executados **231 testes de backend**, smoke tests das imagens de API/worker/web, validação externa de `/ready`, backup pré-produção e backup do estado `produção-zero`.

## Produção ativa

### Infraestrutura

- VPS de produção ativa;
- domínio `smartfoodia.com.br`;
- Caddy como proxy reverso;
- HTTPS válido;
- PostgreSQL 17 saudável;
- API saudável;
- worker ativo;
- frontend ativo;
- Alembic em `0023 (head)`.

### WhatsApp Cloud / Olívia

Estado: **ativo em produção**.

- conta WhatsApp Cloud oficial da Old Burguer 87 cadastrada e ativa;
- webhook público validado;
- token de produção validado;
- mensagens de texto e imagem recebidas pelo número oficial;
- Olívia operacional no canal real;
- atendimento humano com `ASSUMIR`, `STATUS`, `RESOLVER` e `DEVOLVER` homologado;
- `LOCALIZAR PEDIDO` implementado para pedidos delivery;
- localização compartilhada pelo cliente é encaminhada ao atendente;
- imagem/documento durante conversa `HUMAN` é encaminhado ao atendente e não é tratado como comprovante PIX.

### PIX

Estado: **hardening concluído e protegido por testes**.

- comprovante analisado e associado ao pedido;
- duplicidade de arquivo e de transação protegida;
- comprovante recusado não pode ser reutilizado para confirmar o mesmo pedido;
- cadeia de acompanhamento após rejeição: cliente, equipe e gerente;
- pedidos PIX `DELIVERY`/`TAKEOUT` só ficam disponíveis ao Consumer após `AUTO_CONFIRMED` ou `HUMAN_CONFIRMED`;
- `NEEDS_REVIEW` e `HUMAN_REJECTED` permanecem bloqueados;
- pedidos agendados continuam respeitando `release_at`.

### Escalonamento humano e gerencial

- espera por humano possui retomada automática pela Olívia;
- gerente recebe escalonamento quando o atendimento não é assumido;
- gerente pode assumir uma conversa escalada recentemente sem abrir essa permissão para atendentes comuns;
- falhas operacionais críticas podem gerar alerta gerencial sem bloquear o monitor operacional;
- alertas normais usam a janela ativa do WhatsApp; fora da janela, o sistema usa o template `alerta_operacional_gerente`.

**Pendência externa:** o template `alerta_operacional_gerente` permanece **Em análise** na Meta em 2026-08-19. Essa pendência não bloqueia Olívia, pedidos, PIX, Consumer ou atendimento humano; afeta apenas alertas proativos ao gerente que precisem iniciar conversa fora da janela permitida.

### Consumer Partner API

Estado: **ativo e homologado**.

Já validado para:

- polling;
- consulta de detalhes;
- TAKEOUT;
- DELIVERY;
- confirmação;
- pronto;
- despacho / Em Rota;
- conclusão;
- callbacks idempotentes;
- proteção contra regressão de status;
- isolamento entre pedidos simultâneos;
- política de liberação de PIX confirmado antes de expor o pedido ao Consumer.

## Virada produtiva de 2026-08-19

Antes do início da operação normal:

- criado backup completo da fase de desenvolvimento;
- criado e validado backup `produção-zero`;
- pedidos, carrinhos, clientes e endereços de teste foram zerados;
- catálogo, equipe, WhatsApp, Consumer, loja e configurações foram preservados;
- imagens anteriores receberam tags `rollback-20260819`;
- imagens novas receberam tags `deploy-832f93e`;
- rollback operacional foi preparado antes da troca;
- produção nova respondeu `HTTP 200` em `/ready` com banco disponível;
- logs iniciais de API e worker não apresentaram erros.

## Gate atual

O projeto saiu da homologação ampliada e entrou em **produção assistida**.

Prioridades imediatas:

1. acompanhar os primeiros pedidos reais e métricas operacionais;
2. testar o template gerencial assim que a Meta aprová-lo;
3. manter observação de fila, Consumer, WhatsApp e logs durante a estabilização;
4. consolidar aprendizados do piloto antes de declarar a V1 estável.

## Documentos principais

- `docs/PROJECT_CONSTITUTION.md`
- `docs/DECISIONS.md`
- `docs/V1_SCOPE.md`
- `docs/ROADMAP.md`
- `docs/PRODUCTION_RUNTIME.md`
- `docs/CONSUMER_PARTNER_API.md`
- `docs/CONSUMER_HOMOLOGATION.md`

## Estado operacional — 2026-08-29

O SmartFoodIA já opera em produção assistida na Old Burguer 87 com WhatsApp Cloud, Olívia, carrinho, checkout, Consumer, retorno de status e takeover humano.

O fluxo principal validado é:

WhatsApp → Olívia → catálogo/carrinho → confirmação → checkout → Consumer → status → cliente.

PIX foi homologado no Consumer com o contrato ONLINE/prepaid.

Na consolidação operacional de 2026-08-29, a migration Alembic era 0022, incluindo composição técnica e snapshot de combos/TRIOs.

O pedido real #000038 validou o Trio Old Jr. no Consumer pelo valor correto de R$ 25,00, eliminando o comportamento anterior de R$ 0,01.

A prioridade atual do roadmap é o Gate I: eficiência operacional e redução do custo da IA, medindo custo por turno, conversa, pedido e percentual sobre o faturamento antes de ampliar a operação.

Documentação principal: docs/ROADMAP.md, docs/PRODUCTION_RUNTIME.md, docs/DECISIONS.md e CHANGELOG.md.
