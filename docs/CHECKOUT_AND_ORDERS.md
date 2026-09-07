# Checkout e pedidos persistentes

<!-- SMARTFOODIA-CHECKOUT-2026-09-07:START -->
## PIX Copia e Cola após checkout — 2026-09-07

Para checkout com `payment_method = PIX`, o total continua sendo calculado e
confirmado pelo Core.

Após checkout bem-sucedido, o canal WhatsApp pode gerar deterministicamente
um PIX Copia e Cola usando `backend/app/services/pix_brcode.py`.

A geração usa o valor exato retornado pelo checkout e um TXID associado ao
número visível do pedido.

A geração do BR Code:

- não é feita pela Olívia;
- não depende de interpretação do modelo;
- não altera o total do pedido;
- não substitui as regras já existentes de validação do comprovante PIX;
- não libera o pedido ao Consumer antes de `AUTO_CONFIRMED` ou
  `HUMAN_CONFIRMED`.

Portanto, gerar/enviar o código para pagamento e confirmar o pagamento
continuam sendo etapas distintas.
<!-- SMARTFOODIA-CHECKOUT-2026-09-07:END -->

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
