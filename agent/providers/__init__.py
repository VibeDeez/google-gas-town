"""Provider detection and initialization."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.providers.base import Provider


def detect_providers() -> dict[str, Provider]:
    """Auto-detect available providers from environment API keys."""
    providers: dict[str, Provider] = {}

    if os.environ.get("ANTHROPIC_API_KEY"):
        from agent.providers.anthropic import AnthropicProvider
        providers["anthropic"] = AnthropicProvider()

    if os.environ.get("OPENAI_API_KEY"):
        from agent.providers.openai import OpenAIProvider
        providers["openai"] = OpenAIProvider()

    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        from agent.providers.google import GoogleProvider
        providers["google"] = GoogleProvider()

    return providers
