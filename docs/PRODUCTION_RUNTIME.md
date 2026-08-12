# Estado real de produção

Última auditoria operacional: **2026-08-12**.

Este documento registra o que está efetivamente executando na VPS e o que já foi homologado na prática. Ele separa três conceitos que não devem ser confundidos:

1. **implementado no código**;
2. **configurado na produção**;
3. **homologado em operação real**.

## Snapshot da VPS

- branch: `main`;
- ambiente: `production`;
- domínio público: `smartfoodia.com.br`;
- HTTPS ativo via Caddy;
- PostgreSQL 17;
- Python 3.12;
- frontend Next.js 16 / React 19;
- migrations Alembic em `0008 (head)` na auditoria original.

## Serviços ativos

- `smartfoodia-api`: ativo e saudável;
- `smartfoodia-worker`: ativo;
- `smartfoodia-web`: ativo;
- `smartfoodia-db`: ativo e saudável;
- `smartfoodia-caddy`: ativo.

## Consumer — estado atual

Estado: **configurado e homologado de ponta a ponta** para a Old Burguer 87.

### Retirada homologada

Fluxo real validado:

```text
PLACED / PLC
→ Confirmed
→ ReadyToPickup
→ Concluded
```

Estados internos persistidos:

```text
READY_FOR_INTEGRATION
→ CONFIRMED
→ READY
→ CONCLUDED
```

### Delivery homologado

Fluxo real validado:

```text
PLACED / PLC
→ Confirmed
→ ReadyToPickup
→ Dispatched
→ Concluded
```

Estados internos persistidos:

```text
READY_FOR_INTEGRATION
→ CONFIRMED
→ READY
→ DISPATCHED
→ CONCLUDED
```

O payload DELIVERY homologado inclui endereço completo, referência, taxa de entrega, `deliveredBy: "Partner"`, `formattedAddress`, coordenadas e bloco de entrega compatível com o Consumer.

### Teste simultâneo de dois pedidos

Em 2026-08-12 foram criados do zero e processados ao mesmo tempo:

- pedido `000019` — TAKEOUT;
- pedido `000020` — DELIVERY.

Os callbacks de status chegaram intercalados, mas cada atualização manteve o UUID correto do pedido. Não houve mistura entre pedidos.

Resultado final:

```text
000019: PLC → CFM → RTP → CON
000020: PLC → CFM → RTP → DSP → CON
```

Todos os eventos ficaram `DELIVERED` e os dois pedidos terminaram em `CONCLUDED`.

### Proteção contra regressão de status

Após os testes foi adicionada proteção no adapter Consumer para impedir regressões como:

```text
CONCLUDED → READY
DISPATCHED → READY
READY → CONFIRMED
```

Estados terminais não são reabertos por callbacks tardios, e regressões de estágio são ignoradas.

### Autenticação observada

O Consumer real envia o token em:

```text
xapikey: TOKEN
```

O backend também aceita:

```text
Authorization: Bearer TOKEN
```

por compatibilidade.

### Rotação de credencial Consumer

A credencial foi rotacionada durante a homologação de 2026-08-11/12 porque a chave antiga havia aparecido em logs históricos anteriores à correção do Caddy.

Durante a rotação foi identificado que o polling já utilizava a chave nova, enquanto o componente do Consumer responsável por alterações manuais de status ainda mantinha a chave antiga em memória. Isso produziu `401 Unauthorized` apenas nos callbacks de status.

Diagnóstico confirmado sem registrar o segredo: a credencial recebida e a credencial configurada tinham hashes diferentes.

A correção operacional foi:

1. gerar nova chave;
2. armazenar somente o hash no SmartFoodIA;
3. salvar a mesma chave na API Parceiro do Consumer;
4. reiniciar completamente o Consumer após a troca;
5. validar polling e callbacks de status com `200 OK`.

Depois do reinício completo, `Confirmed`, `ReadyToPickup`, `Dispatched` e `Concluded` passaram a usar a nova credencial corretamente.

### Callback de status

A rota observada na operação real é:

```text
POST /api/v1/integrations/consumer/{store_slug}/orders/status
```

O `OrderId` vem no corpo JSON.

A rota com UUID no caminho permanece disponível como compatibilidade:

```text
POST /api/v1/integrations/consumer/{store_slug}/orders/{order_id}/status
```

### Consulta de detalhes

O Consumer consulta:

```text
GET /api/v1/integrations/consumer/{store_slug}/orders/{order_id}
```

Essa consulta marca o `PLC / PLACED` pendente como entregue no fluxo homologado.

### Normalização de status

Mapeamentos aceitos/homologados:

- `Confirmed` → `CONFIRMED`;
- `ReadyToPickup` / `READY_TO_PICKUP` → `READY`;
- `ReadyForPickup` / `READY_FOR_PICKUP` → `READY`;
- `Dispatched` → `DISPATCHED`;
- `OutForDelivery` / `OUT_FOR_DELIVERY` → `DISPATCHED`;
- `Concluded` → `CONCLUDED`;
- `Delivered` → `CONCLUDED`;
- `Cancelled` → `CANCELLED`.

## Segurança de logs

Estado: **corrigido para novos logs**.

Medidas aplicadas:

- removido log de payload bruto de callback de status;
- Caddy configurado para não persistir `Xapikey` no access log;
- teste com chave falsa confirmou que o valor do token não aparece em novos logs;
- diagnósticos temporários de autenticação e status usados na homologação foram removidos do código em 2026-08-12;
- após a remoção, o polling continuou respondendo `200 OK`.

A cópia temporária da nova chave no computador Windows utilizado na operação foi removida e a área de transferência foi limpa.

## OpenAI / Olívia

Estado: **configurado e operacional na VPS**.

Validações executadas em 2026-08-11/12:

- `OPENAI_API_KEY` configurada no ambiente;
- modelo `gpt-5.5` disponível e utilizado;
- chamada direta à OpenAI respondeu com sucesso;
- Olívia respondeu pelo runtime real;
- 13 tools carregadas;
- `search_catalog` validado com catálogo real;
- `get_product` validado com complementos reais;
- carrinho validado com produto + complementos;
- `checkout_cart` bloqueado antes de confirmação explícita;
- checkout real homologado após confirmação explícita;
- pedidos TAKEOUT e DELIVERY criados pela Olívia chegaram corretamente ao Consumer.

A Olívia não inventa preços ou complementos: os dados utilizados nos testes vieram do Core e do catálogo importado.

## Catálogo e complementos

O catálogo rico do Consumer foi importado a partir do arquivo `.prodcon` real.

Última importação auditada:

- versão Consumer: `16.1.0.6`;
- produtos no arquivo: `212`;
- detalhes de produtos: `264`;
- complementos no arquivo: `40`;
- vínculos no arquivo: `1849`;
- grupos criados: `129`;
- produtos com complementos: `129`;
- vínculos grupo-item criados: `1849`;
- produtos locais não encontrados: `0`;
- detalhes de complemento não encontrados: `0`.

O produto AMERICANO foi validado com complementos reais, incluindo Bacon e Queijo, e esses códigos PDV chegaram corretamente ao Consumer nos pedidos de teste.

## WhatsApp

Estado do código: **implementado**.

Estado de produção até esta auditoria:

- canal real ainda não configurado;
- nenhuma conta WhatsApp Cloud ativa havia sido cadastrada na última verificação;
- o fluxo Consumer → SmartFoodIA está homologado, mas a notificação final ao cliente depende da ativação do canal.

Esse é o próximo grande gate operacional.

## Exposição pública atual

Via Caddy estão publicados para o backend:

- `/api/*`;
- `/live`;
- `/ready`.

Para diagnóstico externo, usar `/ready` e os endpoints sob `/api/...`.

## Gates atuais

Situação em **2026-08-12**:

- Gate A — DNS público: **concluído**;
- Gate B — HTTPS público: **concluído**;
- Gate C — diagnóstico API Parceiro: **concluído**;
- Gate D — configuração no Consumer: **concluído**;
- Gate E — pedido controlado: **concluído**;
- Gate F — retorno de status: **concluído para retirada e delivery**;
- Gate G — homologação ampliada: **avançada / em andamento**;
- Gate H — produção assistida via WhatsApp: **pendente**.

## Próximo passo operacional

Configurar a conta WhatsApp Cloud da Old Burguer 87 e homologar o fluxo completo sem comandos manuais:

```text
WhatsApp real
→ Olívia
→ catálogo / cliente / endereço / carrinho
→ confirmação explícita
→ checkout
→ Consumer
→ mudanças de status
→ SmartFoodIA
→ mensagem ao cliente
```
