from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cart import Cart
from app.models.catalog import Store
from app.models.customer import CustomerAddress
from app.models.order import Order, OrderEvent, OrderItem, OrderItemModifier
from app.repositories.cart import CartRepository
from app.repositories.customer import CustomerRepository
from app.repositories.order import OrderRepository
from app.schemas.order import CheckoutRequest, OrderRead
from app.services.commercial_status import CommercialStatusService


class CheckoutValidationError(ValueError):
    pass


OLD_BURGUER_SLUG = "old-burguer-87"
OLD_BURGUER_DELIVERY_FEE = Decimal("3.00")
OLD_BURGUER_MINIMUM_DELIVERY_SUBTOTAL = Decimal("15.00")


class CheckoutService:
    def __init__(
        self,
        cart_repository: CartRepository | None = None,
        customer_repository: CustomerRepository | None = None,
        order_repository: OrderRepository | None = None,
    ) -> None:
        self.cart_repository = cart_repository or CartRepository()
        self.customer_repository = customer_repository or CustomerRepository()
        self.order_repository = order_repository or OrderRepository()

    def checkout(
        self,
        db: Session,
        *,
        cart_id: UUID,
        payload: CheckoutRequest,
    ) -> OrderRead:
        existing = self.order_repository.get_by_cart(db, cart_id)
        if existing is not None:
            return self._to_dto(existing)

        cart = self.cart_repository.get(db, cart_id)
        if cart is None:
            raise CheckoutValidationError("Carrinho não encontrado.")
        if cart.status != "OPEN":
            raise CheckoutValidationError("Carrinho não está aberto.")
        if not cart.items:
            raise CheckoutValidationError("Carrinho vazio.")

        customer = self.customer_repository.get(db, cart.customer_id)
        if customer is None:
            raise CheckoutValidationError("Cliente não encontrado.")

        store = db.scalar(select(Store).where(Store.id == cart.store_id))
        if store is None:
            raise CheckoutValidationError("Loja não encontrada.")

        address = self._resolve_address(db, cart, payload)
        subtotal = self._calculate_subtotal(cart)

        commercial = CommercialStatusService()
        rules = commercial.get_or_create_rules(db, cart.store_id)

        current_status = commercial.current_status(
            db,
            cart.store_id,
            service_mode=cart.service_mode,
        )
        if not current_status["open"]:
            raise CheckoutValidationError(
                f"Não é possível finalizar agora: {current_status['reason']}"
            )

        minimum_delivery = Decimal(rules.minimum_delivery_subtotal)

        if cart.service_mode == "DELIVERY":
            if subtotal < minimum_delivery:
                missing = minimum_delivery - subtotal
                raise CheckoutValidationError(
                    f"Pedido mínimo para entrega é R$ {minimum_delivery:.2f} "
                    "em produtos, sem contar a taxa. "
                    f"Faltam R$ {missing:.2f} em produtos para atingir o mínimo."
                )

            delivery_fee = commercial.delivery_fee(
                db,
                cart.store_id,
                address.neighborhood if address else None,
            )
        else:
            delivery_fee = Decimal("0.00")

        payment_allowed = {
            "PIX": rules.accepts_pix,
            "CREDIT": rules.accepts_credit,
            "DEBIT": rules.accepts_debit,
            "CASH": rules.accepts_cash,
        }

        if not payment_allowed.get(payload.payment_method, False):
            raise CheckoutValidationError(
                "Esta forma de pagamento não está habilitada para a loja."
            )

        if (
            payload.payment_method == "CASH"
            and payload.change_for is not None
            and not rules.allow_change
        ):
            raise CheckoutValidationError(
                "A loja não está aceitando solicitação de troco."
            )

        total = subtotal + delivery_fee - payload.discount
        if total < 0:
            raise CheckoutValidationError("O desconto não pode superar o total.")

        if payload.payment_method == "CASH" and payload.change_for is not None:
            if payload.change_for < total:
                raise CheckoutValidationError(
                    "O valor informado para troco é menor que o total do pedido."
                )

        display_id = self.order_repository.next_display_id(db, cart.store_id)
        order = Order(
            store_id=cart.store_id,
            customer_id=cart.customer_id,
            cart_id=cart.id,
            display_id=display_id,
            status="READY_FOR_INTEGRATION",
            service_mode=cart.service_mode,
            payment_method=payload.payment_method,
            payment_type=payload.payment_type,
            change_for=payload.change_for,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            discount=payload.discount,
            total=total,
            customer_name=customer.name,
            customer_phone=customer.phone,
            address_street=address.street if address else None,
            address_number=address.number if address else None,
            address_neighborhood=address.neighborhood if address else None,
            address_city=address.city if address else None,
            address_state=address.state if address else None,
            address_postal_code=address.postal_code if address else None,
            address_complement=address.complement if address else None,
            address_reference=address.reference if address else None,
        )
        db.add(order)
        db.flush()

        for cart_item in cart.items:
            modifiers_total = sum(
                modifier.unit_price * modifier.quantity
                for modifier in cart_item.modifiers
            )
            item_total = (
                cart_item.unit_price + modifiers_total
            ) * cart_item.quantity
            order_item = OrderItem(
                order_id=order.id,
                product_id=cart_item.product_id,
                product_external_code=cart_item.product_external_code,
                product_name=cart_item.product_name,
                quantity=cart_item.quantity,
                unit_price=cart_item.unit_price,
                total_price=item_total,
                observations=cart_item.observations,
            )
            db.add(order_item)
            db.flush()

            for cart_modifier in cart_item.modifiers:
                db.add(
                    OrderItemModifier(
                        order_item_id=order_item.id,
                        modifier_id=cart_modifier.modifier_id,
                        modifier_external_code=cart_modifier.modifier_external_code,
                        modifier_name=cart_modifier.modifier_name,
                        quantity=cart_modifier.quantity,
                        unit_price=cart_modifier.unit_price,
                        total_price=cart_modifier.unit_price
                        * cart_modifier.quantity,
                    )
                )

        db.add(
            OrderEvent(
                order_id=order.id,
                code="PLC",
                full_code="PLACED",
                status="PENDING",
            )
        )
        cart.status = "CHECKED_OUT"
        db.commit()
        persisted = self.order_repository.get(db, order.id)
        return self._to_dto(persisted)

    def get(self, db: Session, order_id: UUID) -> OrderRead:
        order = self.order_repository.get(db, order_id)
        if order is None:
            raise CheckoutValidationError("Pedido não encontrado.")
        return self._to_dto(order)

    @staticmethod
    def _resolve_address(
        db: Session,
        cart: Cart,
        payload: CheckoutRequest,
    ) -> CustomerAddress | None:
        if cart.service_mode == "TAKEOUT":
            return None
        if payload.address_id is None:
            raise CheckoutValidationError(
                "Endereço é obrigatório para pedido de entrega."
            )
        statement = select(CustomerAddress).where(
            CustomerAddress.id == payload.address_id,
            CustomerAddress.customer_id == cart.customer_id,
            CustomerAddress.active.is_(True),
        )
        address = db.scalar(statement)
        if address is None:
            raise CheckoutValidationError("Endereço inválido para este cliente.")
        return address

    @staticmethod
    def _calculate_subtotal(cart: Cart) -> Decimal:
        subtotal = Decimal("0.00")
        for item in cart.items:
            modifiers_total = sum(
                modifier.unit_price * modifier.quantity
                for modifier in item.modifiers
            )
            subtotal += (item.unit_price + modifiers_total) * item.quantity
        return subtotal

    @staticmethod
    def _to_dto(order: Order) -> OrderRead:
        address = None
        if order.address_street is not None:
            address = {
                "street": order.address_street,
                "number": order.address_number,
                "neighborhood": order.address_neighborhood,
                "city": order.address_city,
                "state": order.address_state,
                "postal_code": order.address_postal_code,
                "complement": order.address_complement,
                "reference": order.address_reference,
            }

        return OrderRead(
            id=order.id,
            display_id=order.display_id,
            status=order.status,
            service_mode=order.service_mode,
            payment_method=order.payment_method,
            payment_type=order.payment_type,
            change_for=order.change_for,
            subtotal=order.subtotal,
            delivery_fee=order.delivery_fee,
            discount=order.discount,
            total=order.total,
            customer_name=order.customer_name,
            customer_phone=order.customer_phone,
            address=address,
            items=[
                {
                    "id": item.id,
                    "external_code": item.product_external_code,
                    "name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price,
                    "observations": item.observations,
                    "modifiers": [
                        {
                            "id": modifier.id,
                            "external_code": modifier.modifier_external_code,
                            "name": modifier.modifier_name,
                            "quantity": modifier.quantity,
                            "unit_price": modifier.unit_price,
                            "total_price": modifier.total_price,
                        }
                        for modifier in item.modifiers
                    ],
                }
                for item in order.items
            ],
        )
