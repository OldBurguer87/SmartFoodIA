from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.ai.usage import extract_openai_usage
from app.core.config import settings
from app.models.catalog import Store
from app.models.conversation import AIEvent


class LookupDeliveryPlaceTool:
    definition = ToolDefinition(
        name="lookup_delivery_place",
        description=(
            "Pesquisa na internet o endereço de um local de entrega conhecido pelo nome "
            "(hotel, pousada, hospital, empresa, órgão público ou ponto comercial) na cidade "
            "da loja. Use imediatamente quando o cliente informar o nome do local, mas disser "
            "que não sabe rua, número ou bairro. NÃO fique insistindo para o cliente descobrir "
            "o endereço antes de usar esta ferramenta. O resultado é apenas uma proposta: "
            "confirme o endereço encontrado com o cliente antes de salvar ou finalizar o pedido."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "place_name": {
                    "type": "string",
                    "minLength": 2,
                    "maxLength": 180,
                    "description": "Nome do hotel, pousada, hospital, empresa ou local informado pelo cliente.",
                }
            },
            "required": ["place_name"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context

    @staticmethod
    def _add_web_search_cost(usage: dict[str, Any] | None) -> dict[str, Any] | None:
        if usage is None:
            return None

        result = dict(usage)
        base = Decimal(str(result.get("estimated_cost_usd") or "0"))
        tool_cost = Decimal("0.01000000")
        result["web_search_calls"] = 1
        result["estimated_web_search_cost_usd"] = str(tool_cost)
        result["estimated_cost_usd"] = str(
            (base + tool_cost).quantize(Decimal("0.00000001"))
        )
        return result

    def execute(self, *, place_name: str, **_: Any) -> ToolResult:
        name = str(place_name or "").strip()
        if len(name) < 2:
            return ToolResult(ok=False, error="Nome do local não informado.")

        store = self.context.db.get(Store, self.context.store_id)
        if store is None:
            return ToolResult(ok=False, error="Loja não encontrada.")

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
            )

            schema = {
                "type": "object",
                "properties": {
                    "found": {"type": "boolean"},
                    "confidence": {
                        "type": "string",
                        "enum": ["HIGH", "MEDIUM", "LOW"],
                    },
                    "canonical_name": {"type": ["string", "null"]},
                    "street": {"type": ["string", "null"]},
                    "number": {"type": ["string", "null"]},
                    "neighborhood": {"type": ["string", "null"]},
                    "city": {"type": ["string", "null"]},
                    "state": {"type": ["string", "null"]},
                    "postal_code": {"type": ["string", "null"]},
                    "source_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 3,
                    },
                },
                "required": [
                    "found",
                    "confidence",
                    "canonical_name",
                    "street",
                    "number",
                    "neighborhood",
                    "city",
                    "state",
                    "postal_code",
                    "source_urls",
                ],
                "additionalProperties": False,
            }

            response = client.responses.create(
                model=settings.openai_model,
                tools=[
                    {
                        "type": "web_search",
                        "search_context_size": "low",
                    }
                ],
                input=(
                    "Pesquise na web somente para localizar com segurança um ponto de entrega. "
                    f"Local informado pelo cliente: {name!r}. "
                    f"Cidade obrigatória: {store.city}, {store.state}, Brasil. "
                    "Não use um resultado de outra cidade. Só marque found=true quando houver "
                    "evidência pública consistente do endereço e rua, número e bairro estiverem "
                    "identificados. Se houver conflito, homônimo, endereço incompleto ou dúvida, "
                    "use found=false ou confidence=LOW. Não invente nenhum campo. "
                    "Inclua até 3 URLs das fontes usadas."
                ),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "delivery_place_lookup",
                        "strict": True,
                        "schema": schema,
                    }
                },
            )

            usage = self._add_web_search_cost(
                extract_openai_usage(
                    response,
                    requested_model=settings.openai_model,
                )
            )

            self.context.db.add(
                AIEvent(
                    store_id=self.context.store_id,
                    conversation_id=self.context.conversation_id,
                    event_type="AI_RESPONSE",
                    tool_name="lookup_delivery_place",
                    success=True,
                    payload_json={
                        "source": "DELIVERY_PLACE_WEB_SEARCH",
                        "place_name": name,
                        "model": str(getattr(response, "model", settings.openai_model)),
                        "usage": usage,
                    },
                )
            )
            self.context.db.commit()

            raw = getattr(response, "output_text", None)
            if not isinstance(raw, str) or not raw.strip():
                return ToolResult(
                    ok=False,
                    error=(
                        "A pesquisa não retornou um endereço estruturado. "
                        "Não invente o endereço e faça uma pergunta curta para avançar."
                    ),
                )

            data = json.loads(raw)
        except Exception as error:
            return ToolResult(
                ok=False,
                error=(
                    "Não consegui consultar o endereço na internet agora. "
                    "Não invente dados; tente uma pergunta curta ou atendimento humano se necessário. "
                    f"Detalhe técnico: {type(error).__name__}."
                ),
            )

        found = bool(data.get("found"))
        confidence = str(data.get("confidence") or "LOW").upper()
        same_city = str(data.get("city") or "").strip().casefold() == store.city.strip().casefold()
        same_state = str(data.get("state") or "").strip().upper() == store.state.strip().upper()
        complete = all(
            str(data.get(field) or "").strip()
            for field in ("street", "number", "neighborhood")
        )

        if not (found and same_city and same_state and complete):
            return ToolResult(
                ok=True,
                data={
                    "found": False,
                    "confidence": "LOW",
                    "place_name": name,
                    "city": store.city,
                    "state": store.state,
                    "confirmation_required": True,
                    "message": (
                        "Não foi possível confirmar um endereço completo e inequívoco na internet. "
                        "Não invente dados. Faça uma pergunta curta para desambiguar ou peça ajuda humana."
                    ),
                },
            )

        return ToolResult(
            ok=True,
            data={
                "found": True,
                "confidence": confidence,
                "place_name": name,
                "canonical_name": data.get("canonical_name") or name,
                "street": data.get("street"),
                "number": data.get("number"),
                "neighborhood": data.get("neighborhood"),
                "city": store.city,
                "state": store.state,
                "postal_code": data.get("postal_code"),
                "source_urls": data.get("source_urls") or [],
                "reference_suggestion": data.get("canonical_name") or name,
                "confirmation_required": True,
                "next_step": (
                    "Pergunte ao cliente se é esse endereço. Somente após confirmação use "
                    "add_customer_address. Para hotel/pousada, use o nome do local como referência "
                    "e quarto/apartamento informado como complemento."
                ),
            },
        )
