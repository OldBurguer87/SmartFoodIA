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

Diferente das versões iniciais, essa ferramenta já persiste um `HumanTicket` e pode criar/incrementar uma `KnowledgeGap` associada à conversa.

## Endpoints

```text
GET  /api/v1/olivia/stores/{store_slug}/tools
POST /api/v1/olivia/stores/{store_slug}/tools/execute
POST /api/v1/olivia/reply
```

## Integração OpenAI

A integração OpenAI já está implementada no código por meio de adaptador próprio. Na auditoria da VPS em 2026-08-11, porém, `OPENAI_CONFIGURED=False`, portanto a Olívia ainda não estava ativa com uma chave OpenAI real em produção.

## Regras

- ferramentas nunca inventam dados;
- valores vêm do Core;
- complementos são validados pelo catálogo;
- checkout exige confirmação explícita;
- erros são devolvidos de forma estruturada;
- a IA não envia pedidos diretamente ao Consumer;
- escalonamento humano persiste trabalho operacional corrigível.

Consulte `docs/PRODUCTION_RUNTIME.md` para distinguir funcionalidade implementada de funcionalidade configurada na VPS.
