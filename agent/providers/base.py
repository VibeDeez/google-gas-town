"""Base types and abstract provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """A tool call requested by the model."""
    id: str
    name: str
    arguments: dict


@dataclass
class CompletionResult:
    """Unified result from any LLM provider."""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    stop_reason: str = ""  # "end_turn", "tool_use", "max_tokens"


@dataclass
class ToolDef:
    """A tool definition that gets converted to each provider's format."""
    name: str
    description: str
    parameters: dict  # JSON Schema


class Provider(ABC):
    """Abstract base for LLM providers."""

    name: str

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        tools: list[ToolDef],
        model: str,
        system: str = "",
        max_tokens: int = 4096,
    ) -> CompletionResult:
        """Send messages to the LLM and return a unified result."""

    @abstractmethod
    def convert_tools(self, tools: list[ToolDef]) -> list[dict]:
        """Convert tool definitions to provider-native format."""
