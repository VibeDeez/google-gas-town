"""Anthropic Claude provider."""

from __future__ import annotations

import json

import anthropic

from agent.providers.base import CompletionResult, Provider, ToolCall, ToolDef


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self):
        self.client = anthropic.Anthropic()

    def complete(
        self,
        messages: list[dict],
        tools: list[ToolDef],
        model: str,
        system: str = "",
        max_tokens: int = 4096,
    ) -> CompletionResult:
        api_messages = self._convert_messages(messages)
        api_tools = self.convert_tools(tools)

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system
        if api_tools:
            kwargs["tools"] = api_tools

        response = self.client.messages.create(**kwargs)

        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))

        stop = "tool_use" if tool_calls else "end_turn"
        if response.stop_reason == "max_tokens":
            stop = "max_tokens"

        return CompletionResult(
            content=content,
            tool_calls=tool_calls,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=model,
            stop_reason=stop,
        )

    def convert_tools(self, tools: list[ToolDef]) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Convert internal message format to Anthropic's format."""
        result = []
        for msg in messages:
            role = msg["role"]

            if role == "user":
                result.append({"role": "user", "content": msg["content"]})

            elif role == "assistant":
                content_blocks = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                for tc in msg.get("tool_calls") or []:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                result.append({"role": "assistant", "content": content_blocks})

            elif role == "tool_result":
                # Anthropic: tool_result blocks go in a user message
                block = {
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": msg["content"],
                }
                if result and result[-1]["role"] == "user" and isinstance(result[-1]["content"], list):
                    result[-1]["content"].append(block)
                else:
                    result.append({"role": "user", "content": [block]})

        return result
