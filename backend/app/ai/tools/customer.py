from __future__ import annotations

from typing import Any

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.repositories.customer import CustomerRepository
from app.schemas.customer import AddressCreate, CustomerCreate
from app.services.customer import CustomerNotFoundError, CustomerService


class FindOrCreateCustomerTool:
    definition = ToolDefinition(
        name="find_or_create_customer",
        description=(
            "Localiza o cliente pelo telefone da conversa ou cria o cadastro. "
            "No WhatsApp, prefira omitir phone porque o sistema já conhece o número do cliente."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"], "minLength": 2},
                "phone": {"type": ["string", "null"], "minLength": 10},
            },
            "required": [],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = CustomerService()
        self.repository = CustomerRepository()

    def execute(
        self,
        *,
        name: str | None = None,
        phone: str | None = None,
        **_: Any,
    ) -> ToolResult:
        resolved_phone = (phone or self.context.customer_phone or "").strip()
        if not resolved_phone:
            return ToolResult(
                ok=False,
                error="Telefone do cliente não está disponível no canal.",
            )

        existing = self.repository.get_by_phone(
            self.context.db,
            store_id=self.context.store_id,
            phone=resolved_phone,
        )
        if existing is not None:
            if name and existing.name != name:
                existing.name = name
                self.context.db.commit()
                self.context.db.refresh(existing)
            return ToolResult(
                ok=True,
                data={
                    "id": str(existing.id),
                    "name": existing.name,
                    "phone": existing.phone,
                    "existing": True,
                    "addresses": [
                        {
                            "id": str(address.id),
                            "label": address.label,
                            "street": address.street,
                            "number": address.number,
                            "neighborhood": address.neighborhood,
                            "city": address.city,
                            "state": address.state,
                            "postal_code": address.postal_code,
                            "complement": address.complement,
                            "reference": address.reference,
                            "is_default": address.is_default,
                        }
                        for address in existing.addresses
                        if address.active
                    ],
                },
            )

        if not name:
            return ToolResult(
                ok=False,
                error="Cliente ainda não cadastrado. Peça somente o nome para continuar.",
                requires_human=False,
            )

        customer = self.service.find_or_create(
            self.context.db,
            CustomerCreate(
                store_id=self.context.store_id,
                name=name,
                phone=resolved_phone,
            ),
        )
        return ToolResult(
            ok=True,
            data={
                "id": str(customer.id),
                "name": customer.name,
                "phone": customer.phone,
                "existing": False,
                "addresses": [],
            },
        )


class ListCustomerAddressesTool:
    definition = ToolDefinition(
        name="list_customer_addresses",
        description="Lista os endereços ativos de um cliente.",
        input_schema={
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "format": "uuid"},
            },
            "required": ["customer_id"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.repository = CustomerRepository()

    def execute(self, *, customer_id: str, **_: Any) -> ToolResult:
        from uuid import UUID

        customer = self.repository.get(self.context.db, UUID(customer_id))
        if customer is None or customer.store_id != self.context.store_id:
            return ToolResult(ok=False, error="Cliente não encontrado.")

        return ToolResult(
            ok=True,
            data={
                "customer_id": customer_id,
                "addresses": [
                    {
                        "id": str(address.id),
                        "label": address.label,
                        "street": address.street,
                        "number": address.number,
                        "neighborhood": address.neighborhood,
                        "city": address.city,
                        "state": address.state,
                        "postal_code": address.postal_code,
                        "complement": address.complement,
                        "reference": address.reference,
                        "is_default": address.is_default,
                    }
                    for address in customer.addresses
                    if address.active
                ],
            },
        )


class AddCustomerAddressTool:
    definition = ToolDefinition(
        name="add_customer_address",
        description="Adiciona um endereço real ao cadastro do cliente.",
        input_schema={
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "format": "uuid"},
                "label": {"type": "string"},
                "street": {"type": "string"},
                "number": {"type": "string"},
                "neighborhood": {"type": "string"},
                "city": {"type": "string"},
                "state": {"type": "string"},
                "postal_code": {"type": ["string", "null"]},
                "complement": {"type": ["string", "null"]},
                "reference": {"type": ["string", "null"]},
                "is_default": {"type": "boolean"},
            },
            "required": [
                "customer_id",
                "street",
                "number",
                "neighborhood",
            ],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = CustomerService()

    def execute(
        self,
        *,
        customer_id: str,
        street: str,
        number: str,
        neighborhood: str,
        label: str = "Principal",
        city: str = "Coari",
        state: str = "AM",
        postal_code: str | None = None,
        complement: str | None = None,
        reference: str | None = None,
        is_default: bool = False,
        **_: Any,
    ) -> ToolResult:
        from uuid import UUID

        try:
            address = self.service.add_address(
                self.context.db,
                customer_id=UUID(customer_id),
                payload=AddressCreate(
                    label=label,
                    street=street,
                    number=number,
                    neighborhood=neighborhood,
                    city=city,
                    state=state,
                    postal_code=postal_code,
                    complement=complement,
                    reference=reference,
                    is_default=is_default,
                ),
            )
        except CustomerNotFoundError:
            return ToolResult(ok=False, error="Cliente não encontrado.")

        return ToolResult(
            ok=True,
            data={
                "id": str(address.id),
                "customer_id": str(address.customer_id),
                "label": address.label,
                "street": address.street,
                "number": address.number,
                "neighborhood": address.neighborhood,
                "city": address.city,
                "state": address.state,
                "is_default": address.is_default,
            },
        )
