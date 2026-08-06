# Checkout e pedidos persistentes

## Finalizar carrinho

```text
POST /api/v1/orders/checkout/{cart_id}
```

Exemplo para entrega com PIX:

```json
{
  "address_id": "UUID_DO_ENDERECO",
  "payment_method": "PIX",
  "payment_type": "PENDING",
  "delivery_fee": 5,
  "discount": 0
}
```

Exemplo em dinheiro:

```json
{
  "address_id": "UUID_DO_ENDERECO",
  "payment_method": "CASH",
  "payment_type": "PENDING",
  "change_for": 100,
  "delivery_fee": 5
}
```

## Regras

- carrinho vazio não finaliza;
- entrega exige endereço válido do cliente;
- retirada não exige endereço;
- troco só é aceito em dinheiro;
- valor para troco deve cobrir o total;
- preços e nomes são copiados para o pedido;
- o carrinho é marcado como `CHECKED_OUT`;
- é criado um evento `PLACED / PLC`;
- repetir o checkout do mesmo carrinho devolve o mesmo pedido.

## Consultar pedido

```text
GET /api/v1/orders/{order_id}
```

O pedido mantém snapshots de cliente, endereço, produtos, complementos e preços.
