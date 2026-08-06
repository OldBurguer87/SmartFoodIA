# Clientes, endereços e carrinho

## Cliente

O cliente é identificado por telefone dentro de cada loja.

O endpoint:

```text
POST /api/v1/customers/find-or-create
```

normaliza o número e devolve o cliente existente ou cria um novo.

## Endereço

```text
POST /api/v1/customers/{customer_id}/addresses
```

O primeiro endereço cadastrado torna-se o endereço padrão.

## Carrinho

```text
POST /api/v1/carts
```

Cria ou recupera o carrinho aberto do cliente.

### Adicionar produto

```text
POST /api/v1/carts/{cart_id}/items
```

Exemplo:

```json
{
  "product_external_code": "235",
  "quantity": 1,
  "observations": "Sem cebola",
  "modifiers": [
    {"external_code": "37", "quantity": 1},
    {"external_code": "39", "quantity": 2}
  ]
}
```

O Core:

- consulta o produto real;
- valida disponibilidade;
- valida compatibilidade dos complementos;
- valida mínimo e máximo dos grupos;
- copia os preços vigentes para o item;
- calcula o subtotal.

A IA nunca calcula ou altera esses valores.

## Alterar e remover

```text
PATCH /api/v1/carts/{cart_id}/items/{item_id}
DELETE /api/v1/carts/{cart_id}/items/{item_id}
DELETE /api/v1/carts/{cart_id}/items
```
