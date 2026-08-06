from dataclasses import dataclass, field
from typing import Any, Protocol

@dataclass(frozen=True)
class ProviderToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]

@dataclass(frozen=True)
class ProviderResponse:
    response_id: str | None
    text: str | None = None
    tool_calls: list[ProviderToolCall] = field(default_factory=list)

class AIProvider(Protocol):
    def respond(self, *, instructions: str, input_items: list[dict[str, Any]],
                tools: list[dict[str, Any]],
                previous_response_id: str | None = None) -> ProviderResponse: ...
