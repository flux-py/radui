from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class MCPToolDescriptor:
    """Descriptor for an MCP tool exposed to RADUI AI agents with security controls."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    handler: Callable[..., Any]
    requires_approval: bool = False
    read_only: bool = True

    def validate_arguments(self, args: dict[str, Any]) -> bool:
        # Schema validation can check required keys
        required = self.parameters_schema.get("required", [])
        return all(key in args for key in required)


class MCPToolRegistry:
    """Registry of tools available for agent invocation and human-in-the-loop validation."""

    def __init__(self) -> None:
        self._tools: dict[str, MCPToolDescriptor] = {}

    def register(self, tool: MCPToolDescriptor) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> MCPToolDescriptor | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.parameters_schema,
                "requires_approval": t.requires_approval,
            }
            for t in self._tools.values()
        ]

