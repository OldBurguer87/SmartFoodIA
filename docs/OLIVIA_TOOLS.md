# Ferramentas da Olívia

## Objetivo

A Olívia não acessa o banco e não executa regras de negócio diretamente.

Ela usa ferramentas autorizadas que chamam os Services do SmartFoodIA.

## Ferramentas disponíveis

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

O checkout exige:

```json
{
  "customer_confirmed": true
}
```

Sem confirmação explícita, o pedido não é criado.

### Suporte humano

- `request_human_help`

Nesta versão ela devolve uma escalação estruturada. A próxima etapa persistirá tickets,
alertas e lacunas de conhecimento no banco.

## Endpoints de desenvolvimento

### Listar definições compatíveis com function calling

```text
GET /api/v1/olivia/stores/{store_slug}/tools
```

### Executar uma ferramenta

```text
POST /api/v1/olivia/stores/{store_slug}/tools/execute
```

Exemplo:

```json
{
  "tool_name": "search_catalog",
  "arguments": {
    "query": "monster",
    "service_mode": "DELIVERY"
  }
}
```

## Regras

- ferramentas nunca inventam dados;
- valores vêm do Core;
- complementos são validados pelo catálogo;
- o checkout exige confirmação explícita;
- erros são devolvidos de forma estruturada;
- a integração OpenAI ainda não está nesta versão.
