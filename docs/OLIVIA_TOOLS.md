# Ferramentas da Olívia

## Objetivo

A Olívia não acessa o banco nem executa regras de negócio diretamente. Ela usa ferramentas autorizadas que chamam os Services do SmartFoodIA.

## Ferramentas disponíveis no código

### Catálogo

- `search_catalog`
- `get_product`

### Cliente

- `find_or_create_customer`
- `list_customer_addresses`
- `add_customer_address`

### Carrinho

- `get_or_create_cart`
- `get_cart`
- `add_cart_item`
- `update_cart_item`
- `remove_cart_item`

### Checkout

- `checkout_cart`

O checkout exige confirmação explícita do cliente:

```json
{
  "customer_confirmed": true
}
```

Sem confirmação, o pedido não é criado.

### Conhecimento

- `search_knowledge`

Essa ferramenta consulta somente respostas aprovadas/resolvidas na base de conhecimento.

### Suporte humano

- `request_human_help`

Essa ferramenta persiste um `HumanTicket` e pode criar/incrementar uma `KnowledgeGap` associada à conversa.

## Endpoints

```text
GET  /api/v1/olivia/stores/{store_slug}/tools
POST /api/v1/olivia/stores/{store_slug}/tools/execute
POST /api/v1/olivia/reply
```

## Integração OpenAI — estado atual

Estado em produção em **2026-08-12**: **operacional**.

Validações executadas:

- `OPENAI_API_KEY` configurada na VPS;
- modelo configurado: `gpt-5.5`;
- chamada direta à OpenAI respondeu com sucesso;
- `/api/v1/olivia/reply` respondeu pelo runtime real;
- 13 tools carregadas;
- `search_catalog` validado com catálogo real;
- `get_product` validado com complementos reais;
- carrinho validado com produto + complementos;
- `checkout_cart` não foi chamado antes da confirmação explícita;
- checkout real foi executado após confirmação explícita.

## Homologação funcional da Olívia

### Catálogo e complementos

O produto AMERICANO foi consultado no catálogo real e os complementos reais foram retornados corretamente.

O carrinho foi montado com:

```text
1x AMERICANO
+ 1x BACON
+ 1x QUEIJO
```

Os preços vieram do Core e os códigos PDV chegaram corretamente ao Consumer.

### TAKEOUT

Fluxo homologado:

```text
Olívia
→ cliente
→ catálogo
→ carrinho
→ confirmação explícita
→ checkout
→ READY_FOR_INTEGRATION
→ Consumer
→ Confirmed
→ ReadyToPickup
→ Concluded
```

### DELIVERY

Fluxo homologado:

```text
Olívia
→ cliente
→ endereço
→ catálogo
→ carrinho
→ taxa de entrega
→ confirmação explícita
→ checkout
→ READY_FOR_INTEGRATION
→ Consumer
→ Confirmed
→ ReadyToPickup
→ Dispatched
→ Concluded
```

No teste homologado, a Olívia criou corretamente delivery com endereço, referência, débito e taxa de entrega de R$ 3,00.

## Regras operacionais confirmadas

- ferramentas nunca inventam dados;
- valores vêm do Core;
- complementos são validados pelo catálogo;
- checkout exige confirmação explícita;
- erros são devolvidos de forma estruturada;
- a IA não envia pedidos diretamente ao Consumer: o pedido é criado no Core e publicado pela integração;
- escalonamento humano persiste trabalho operacional corrigível;
- a Olívia pode montar e finalizar pedidos reais de TAKEOUT e DELIVERY quando as informações necessárias e a confirmação do cliente estiverem presentes.

## Pendência principal

A Olívia já está operacional no backend, mas o **canal WhatsApp real ainda não está configurado**.

O próximo teste deve validar o mesmo fluxo homologado sem comandos manuais:

```text
WhatsApp real
→ Olívia
→ tools
→ checkout
→ Consumer
→ retorno de status
→ mensagem ao cliente
```

Consulte `docs/PRODUCTION_RUNTIME.md` para o estado efetivamente auditado da VPS.
