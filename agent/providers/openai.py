"""OpenAI GPT provider."""

from __future__ import annotations

import json
import uuid

from openai import OpenAI

from agent.providers.base import CompletionResult, Provider, ToolCall, ToolDef


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self):
        self.client = OpenAI()

    def complete(
        self,
        messages: list[dict],
        tools: list[ToolDef],
        model: str,
        system: str = "",
        max_tokens: int = 4096,
    ) -> CompletionResult:
        api_messages = self._convert_messages(messages, system)
        api_tools = self.convert_tools(tools)

        kwargs: dict = {
            "model": model,
            "messages": api_messages,
            "max_completion_tokens": max_tokens,
        }
        if api_tools:
            kwargs["tools"] = api_tools

        response = self.client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        stop = "tool_use" if tool_calls else "end_turn"
        if choice.finish_reason == "length":
            stop = "max_tokens"

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        return CompletionResult(
            content=content,
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            stop_reason=stop,
        )

    def convert_tools(self, tools: list[ToolDef]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _convert_messages(self, messages: list[dict], system: str = "") -> list[dict]:
        """Convert internal message format to OpenAI's format."""
        result = []
        if system:
            result.append({"role": "system", "content": system})

        for msg in messages:
            role = msg["role"]

            if role == "user":
                result.append({"role": "user", "content": msg["content"]})

            elif role == "assistant":
                m: dict = {"role": "assistant"}
                if msg.get("content"):
                    m["content"] = msg["content"]
                if msg.get("tool_calls"):
                    m["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ]
                result.append(m)

            elif role == "tool_result":
                result.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg["content"],
                })

        return result
