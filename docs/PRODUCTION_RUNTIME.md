# Estado real de produção

Última auditoria operacional: **2026-08-19**.

Este documento registra o que está efetivamente executando na VPS e separa três conceitos:

1. **implementado no código**;
2. **configurado na produção**;
3. **homologado em operação real**.

## Snapshot da VPS

- branch operacional: `feature/plataforma-multiempresa`;
- commit implantado: **`832f93e`**;
- ambiente: `production`;
- domínio público: `smartfoodia.com.br`;
- HTTPS ativo via Caddy;
- PostgreSQL 17;
- Python 3.12;
- frontend Next.js 16 / React 19;
- Alembic: **`0017 (head)`**;
- backend: **231 testes aprovados** antes da virada de 2026-08-19.

## Serviços ativos após a virada

- `smartfoodia-api`: ativo e saudável;
- `smartfoodia-worker`: ativo;
- `smartfoodia-web`: ativo;
- `smartfoodia-db`: ativo e saudável;
- `smartfoodia-caddy`: ativo.

Validação externa pós-deploy:

```text
GET https://smartfoodia.com.br/ready
HTTP 200
{"status":"ready","application":"SmartFoodIA","database":"available"}
```

Os logs iniciais da API e do worker não apresentaram `ERROR`, exception ou traceback após a troca.

## Imagens e rollback

Antes da virada, as imagens em execução foram preservadas com as tags:

```text
smartfoodia-api:rollback-20260819
smartfoodia-worker:rollback-20260819
smartfoodia-web:rollback-20260819
```

As novas imagens foram preservadas como:

```text
smartfoodia-api:deploy-832f93e
smartfoodia-worker:deploy-832f93e
smartfoodia-web:deploy-832f93e
```

Foi criado um script de rollback operacional em `/root/smartFoodIA/rollback-20260819.sh` antes da troca dos containers.

## Backups da virada

Foram criados e validados dois marcos:

1. **pré-produção/desenvolvimento** — estado completo anterior à limpeza dos dados de teste;
2. **produção-zero** — estado imediatamente após a limpeza dos dados operacionais de teste e antes da operação normal.

Os dumps foram gerados em formato custom do PostgreSQL, validados por SHA-256 e listados com `pg_restore` dentro do container PostgreSQL.

Na limpeza de virada foram zerados:

- pedidos;
- itens/eventos dependentes de pedidos;
- carrinhos;
- clientes;
- endereços.

Foram preservados:

- catálogo;
- loja;
- equipe;
- conta WhatsApp;
- integração Consumer;
- horários e regras comerciais;
- conversas e tickets históricos;
- configurações.

Após a limpeza, a base confirmou:

```text
pedidos = 0
clientes = 0
enderecos = 0
carrinhos = 0
produtos_ativos = 107
equipe_ativa = 2
canais_ativos = 1
integracoes_ativas = 1
lojas = 1
```

## Consumer — estado atual

Estado: **ativo e homologado**.

A integração continua usando o Consumer como adapter, sem mover regras do Core para o ERP.

### Fluxos homologados

Retirada:

```text
PLACED / PLC
→ Confirmed
→ ReadyToPickup
→ Concluded
```

Delivery:

```text
PLACED / PLC
→ Confirmed
→ ReadyToPickup
→ Dispatched
→ Concluded
```

Proteções vigentes:

- callbacks idempotentes;
- estados terminais não reabrem;
- regressões de estágio são ignoradas;
- pedidos simultâneos preservam seus UUIDs;
- `release_at` controla liberação de pedidos agendados.

### Regra PIX antes do Consumer

Desde o commit `832f93e`, pedidos com:

```text
payment_method = PIX
service_mode = DELIVERY ou TAKEOUT
```

só ficam disponíveis ao Consumer se existir `PaymentReceipt` com status:

```text
AUTO_CONFIRMED
ou
HUMAN_CONFIRMED
```

Estados como:

```text
NEEDS_REVIEW
HUMAN_REJECTED
```

não liberam polling, detalhes ou callbacks diretos do Consumer.

Pagamentos não-PIX mantêm o comportamento anterior.

Após o deploy, `store_integrations.updated_at` continuou sendo renovado, confirmando polling Consumer ativo pelo worker novo.

## WhatsApp Cloud

Estado: **ativo em produção**.

Conta ativa:

```text
provider = WHATSAPP_CLOUD
Phone Number ID = 1244010068798110
```

A migração do número oficial foi homologada com:

- webhook ativo;
- token de produção funcional;
- texto recebido e respondido;
- imagem recebida;
- mensagens outbound chegando ao cliente;
- atendimento humano pelo número da equipe.

Registros `DEAD`/`FAILED` encontrados durante a auditoria de virada eram históricos de desenvolvimento de 2026-08-12/17, anteriores à produção atual. Não houve evento novo problemático após a troca do runtime.

## Olívia

Estado: **operacional no canal real**.

Já homologado:

- contexto conversacional;
- catálogo real;
- complementos;
- carrinho;
- confirmação explícita;
- TAKEOUT;
- DELIVERY;
- taxa de entrega;
- status do Consumer;
- atendimento humano e retomada.

## Atendimento humano

Comandos homologados incluem:

```text
ASSUMIR
STATUS
RESOLVER
DEVOLVER
LOCALIZAR PEDIDO
```

### Retomada automática

Uma conversa em `WAITING_HUMAN` que não for assumida dentro do timeout operacional pode voltar à Olívia. A retomada não depende do gerente para continuar o atendimento.

### Escalonamento gerencial

O gerente possui fila de notificação separada da equipe comum.

Situações cobertas:

- atendimento não assumido;
- etapa final da cadeia de PIX rejeitado;
- novos incidentes críticos detectados pelo monitor operacional.

Um gerente pode assumir por até 30 minutos uma conversa `OPEN` que tenha sido recentemente escalada. Essa exceção não é concedida a atendentes comuns.

## Mídia e localização em atendimento humano

Durante status `HUMAN`:

- imagem/documento recebido do cliente é encaminhado ao atendente;
- essa mídia não passa pelo fluxo de comprovante PIX;
- conversa `HUMAN` sem atendente vinculado falha de forma segura;
- localização do WhatsApp é convertida em contexto textual com latitude, longitude e link de mapa e encaminhada ao atendente.

## LOCALIZAR PEDIDO

Para pedidos `DELIVERY`, o atendente pode localizar o pedido pelo display ID e assumir a conversa correspondente para solicitar localização/foto/referência do cliente.

Proteções incluem:

- pedido inexistente;
- pedido não-delivery;
- conversa encerrada/incompatível;
- não roubar conversa de outro atendente;
- restrição de contexto ao pedido e telefone corretos.

## PIX — revisão e escalonamento

Proteções atuais:

- SHA-256 de arquivo;
- fingerprint/transação para antifraude;
- comprovante rejeitado não pode ser reutilizado para confirmar o pedido;
- nova transação interrompe a cadeia antiga de rejeição.

Após `HUMAN_REJECTED` e ausência de novo comprovante:

```text
5 min  → lembrete ao cliente
10 min → alerta à equipe
15 min → escalonamento ao gerente
```

Não há cancelamento automático do pedido nessa cadeia.

## Alertas operacionais críticos

`OperationalMonitorService` detecta problemas de:

- OpenAI;
- WhatsApp/Meta;
- Consumer;
- fila operacional.

Um novo incidente cria ticket `SYSTEM / URGENT` e tenta alertar o gerente. A mesma falha persistente reutiliza o ticket e não dispara alerta duplicado em cada ciclo.

Falha na notificação ao gerente não impede o monitor de registrar o incidente.

## Template gerencial da Meta

Template configurado:

```text
alerta_operacional_gerente
idioma: pt_BR
categoria: Utilidade
```

Status em **2026-08-19**: **Em análise**.

Dentro da janela ativa do WhatsApp, o gerente pode receber texto normal. Fora dela, o sistema tenta o template aprovado. Enquanto a Meta não aprovar o template, essa parte específica pode falhar sem bloquear o atendimento principal.

## Segurança e segredos

- tokens e credenciais não devem ser exibidos em logs/documentação;
- `.env` e backups são restritos ao servidor;
- credencial Consumer permanece armazenada de forma segura;
- access log do Caddy não deve persistir `xapikey`;
- backups de virada incluem `.env` protegido, mas seu conteúdo não deve ser exibido.

## Estado dos gates

Situação em **2026-08-19**:

- Gate A — DNS público: **concluído**;
- Gate B — HTTPS público: **concluído**;
- Gate C — diagnóstico API Parceiro: **concluído**;
- Gate D — configuração Consumer: **concluído**;
- Gate E — pedido controlado: **concluído**;
- Gate F — retorno de status: **concluído**;
- Gate G — homologação ampliada: **concluída para entrada em produção assistida**;
- Gate H — WhatsApp oficial: **concluído**;
- Gate I — produção assistida: **ativa**.

## Próximo passo operacional

Não fazer mudanças desnecessárias durante a estabilização.

Prioridades:

1. observar primeiros pedidos reais completos;
2. acompanhar logs, filas e Consumer;
3. validar o template gerencial quando a Meta decidir;
4. registrar incidentes reais e corrigir somente problemas reproduzíveis;
5. após período de estabilidade, declarar os critérios da V1 cumpridos.
