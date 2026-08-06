from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    requires_human: bool = False


class OliviaTool(Protocol):
    definition: ToolDefinition

    def execute(self, **kwargs: Any) -> ToolResult:
        ...
