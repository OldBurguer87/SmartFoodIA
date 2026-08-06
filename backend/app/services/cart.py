from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cart import Cart, CartItem, CartItemModifier
from app.models.catalog import Modifier, ModifierGroup, Product
from app.repositories.cart import CartRepository
from app.repositories.catalog import ProductRepository
from app.repositories.customer import CustomerRepository
from app.schemas.cart import CartItemAdd, CartItemUpdate, CartRead


class CartNotFoundError(LookupError):
    pass


class CartValidationError(ValueError):
    pass


class CartService:
    def __init__(
        self,
        cart_repository: CartRepository | None = None,
        product_repository: ProductRepository | None = None,
        customer_repository: CustomerRepository | None = None,
    ) -> None:
        self.cart_repository = cart_repository or CartRepository()
        self.product_repository = product_repository or ProductRepository()
        self.customer_repository = customer_repository or CustomerRepository()

    def create_or_get_open(
        self,
        db: Session,
        *,
        store_id: UUID,
        customer_id: UUID,
        service_mode: str,
    ) -> CartRead:
        customer = self.customer_repository.get(db, customer_id)
        if customer is None or customer.store_id != store_id:
            raise CartValidationError("Cliente não pertence à loja informada.")

        cart = self.cart_repository.get_open_for_customer(
            db,
            store_id=store_id,
            customer_id=customer_id,
        )
        if cart is None:
            cart = self.cart_repository.create(
                db,
                store_id=store_id,
                customer_id=customer_id,
                service_mode=service_mode,
            )
        elif cart.service_mode != service_mode:
            cart.service_mode = service_mode
            db.commit()
            cart = self._get_cart(db, cart.id)
        return self._to_dto(cart)

    def get(self, db: Session, cart_id: UUID) -> CartRead:
        return self._to_dto(self._get_cart(db, cart_id))

    def add_item(
        self,
        db: Session,
        *,
        cart_id: UUID,
        payload: CartItemAdd,
    ) -> CartRead:
        cart = self._get_open_cart(db, cart_id)
        product = self.product_repository.get_detailed_by_external_code(
            db,
            store_id=cart.store_id,
            external_code=payload.product_external_code,
        )
        if product is None or not product.active:
            raise CartValidationError("Produto não encontrado ou indisponível.")

        if cart.service_mode == "DELIVERY" and not product.available_for_delivery:
            raise CartValidationError("Produto indisponível para entrega.")
        if cart.service_mode == "TAKEOUT" and not product.available_for_takeout:
            raise CartValidationError("Produto indisponível para retirada.")

        selected_modifiers = self._validate_modifiers(db, product, payload)
        item = CartItem(
            cart_id=cart.id,
            product_id=product.id,
            product_external_code=product.external_code,
            product_name=product.name,
            quantity=payload.quantity,
            unit_price=product.price,
            observations=payload.observations,
        )
        db.add(item)
        db.flush()

        for modifier, quantity in selected_modifiers:
            db.add(
                CartItemModifier(
                    cart_item_id=item.id,
                    modifier_id=modifier.id,
                    modifier_external_code=modifier.external_code,
                    modifier_name=modifier.name,
                    quantity=quantity,
                    unit_price=modifier.price,
                )
            )

        db.commit()
        return self.get(db, cart.id)

    def update_item(
        self,
        db: Session,
        *,
        cart_id: UUID,
        item_id: UUID,
        payload: CartItemUpdate,
    ) -> CartRead:
        cart = self._get_open_cart(db, cart_id)
        item = next((current for current in cart.items if current.id == item_id), None)
        if item is None:
            raise CartValidationError("Item não pertence ao carrinho.")
        item.quantity = payload.quantity
        item.observations = payload.observations
        db.commit()
        return self.get(db, cart.id)

    def remove_item(
        self,
        db: Session,
        *,
        cart_id: UUID,
        item_id: UUID,
    ) -> CartRead:
        cart = self._get_open_cart(db, cart_id)
        item = next((current for current in cart.items if current.id == item_id), None)
        if item is None:
            raise CartValidationError("Item não pertence ao carrinho.")
        db.delete(item)
        db.commit()
        return self.get(db, cart.id)

    def clear(self, db: Session, cart_id: UUID) -> CartRead:
        cart = self._get_open_cart(db, cart_id)
        for item in list(cart.items):
            db.delete(item)
        db.commit()
        return self.get(db, cart.id)

    def _get_cart(self, db: Session, cart_id: UUID) -> Cart:
        cart = self.cart_repository.get(db, cart_id)
        if cart is None:
            raise CartNotFoundError(str(cart_id))
        return cart

    def _get_open_cart(self, db: Session, cart_id: UUID) -> Cart:
        cart = self._get_cart(db, cart_id)
        if cart.status != "OPEN":
            raise CartValidationError("Carrinho não está aberto.")
        return cart

    def _validate_modifiers(
        self,
        db: Session,
        product: Product,
        payload: CartItemAdd,
    ) -> list[tuple[Modifier, int]]:
        requested: dict[str, int] = defaultdict(int)
        for selection in payload.modifiers:
            requested[selection.external_code] += selection.quantity

        allowed: dict[str, tuple[Modifier, UUID]] = {}
        group_rules: dict[UUID, tuple[ModifierGroup, int, int]] = {}

        for product_link in product.modifier_group_links:
            group = product_link.group
            if not group.active:
                continue
            minimum = (
                product_link.min_select_override
                if product_link.min_select_override is not None
                else group.min_select
            )
            maximum = (
                product_link.max_select_override
                if product_link.max_select_override is not None
                else group.max_select
            )
            group_rules[group.id] = (group, minimum, maximum)
            for group_item in group.modifier_links:
                modifier = group_item.modifier
                if modifier.active:
                    allowed[modifier.external_code] = (modifier, group.id)

        unknown = sorted(set(requested).difference(allowed))
        if unknown:
            raise CartValidationError(
                "Complementos incompatíveis com o produto: " + ", ".join(unknown)
            )

        group_quantities: dict[UUID, int] = defaultdict(int)
        result: list[tuple[Modifier, int]] = []
        for external_code, quantity in requested.items():
            modifier, group_id = allowed[external_code]
            group_quantities[group_id] += quantity
            result.append((modifier, quantity))

        for group_id, (group, minimum, maximum) in group_rules.items():
            selected = group_quantities[group_id]
            if selected < minimum:
                raise CartValidationError(
                    f"O grupo '{group.name}' exige no mínimo {minimum} seleção(ões)."
                )
            if selected > maximum:
                raise CartValidationError(
                    f"O grupo '{group.name}' permite no máximo {maximum} seleção(ões)."
                )

        return result

    @staticmethod
    def _to_dto(cart: Cart) -> CartRead:
        item_dtos = []
        subtotal = Decimal("0.00")

        for item in cart.items:
            modifier_dtos = []
            modifiers_unit_total = Decimal("0.00")
            for modifier in item.modifiers:
                modifier_total = modifier.unit_price * modifier.quantity
                modifiers_unit_total += modifier_total
                modifier_dtos.append(
                    {
                        "id": modifier.id,
                        "external_code": modifier.modifier_external_code,
                        "name": modifier.modifier_name,
                        "quantity": modifier.quantity,
                        "unit_price": modifier.unit_price,
                        "total": modifier_total,
                    }
                )

            item_total = (item.unit_price + modifiers_unit_total) * item.quantity
            subtotal += item_total
            item_dtos.append(
                {
                    "id": item.id,
                    "product_external_code": item.product_external_code,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "observations": item.observations,
                    "modifiers": modifier_dtos,
                    "total": item_total,
                }
            )

        return CartRead(
            id=cart.id,
            store_id=cart.store_id,
            customer_id=cart.customer_id,
            status=cart.status,
            service_mode=cart.service_mode,
            items=item_dtos,
            subtotal=subtotal,
        )
