from __future__ import annotations

from typing import Any

from app.ai.tools.cart import (
    AddCartItemTool,
    GetCartTool,
    GetOrCreateCartTool,
    RemoveCartItemTool,
    UpdateCartItemTool,
)
from app.ai.tools.catalog import (
    BrowseCatalogTool,
    GetProductTool,
    SearchCatalogTool,
)
from app.ai.tools.checkout import CheckoutCartTool
from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.ai.tools.customer import (
    AddCustomerAddressTool,
    FindOrCreateCustomerTool,
    ListCustomerAddressesTool,
)
from app.ai.tools.support import RequestHumanHelpTool
from app.ai.tools.menu_document import SendMenuPdfTool
from app.ai.tools.knowledge import SearchKnowledgeTool


class UnknownToolError(LookupError):
    pass


class OliviaToolRegistry:
    def __init__(self, context: ToolContext) -> None:
        tools = [
            BrowseCatalogTool(context),
            SearchCatalogTool(context),
            GetProductTool(context),
            FindOrCreateCustomerTool(context),
            ListCustomerAddressesTool(context),
            AddCustomerAddressTool(context),
            GetOrCreateCartTool(context),
            GetCartTool(context),
            AddCartItemTool(context),
            UpdateCartItemTool(context),
            RemoveCartItemTool(context),
            CheckoutCartTool(context),
            SearchKnowledgeTool(context),
            SendMenuPdfTool(context),
            RequestHumanHelpTool(context),
        ]
        self._tools = {tool.definition.name: tool for tool in tools}

    def definitions(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]

    def openai_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.input_schema,
                },
            }
            for definition in self.definitions()
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError(name)
        return tool.execute(**arguments)
