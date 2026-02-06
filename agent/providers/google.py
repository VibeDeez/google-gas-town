"""Google Gemini provider."""

from __future__ import annotations

import os
import uuid

from google import genai
from google.genai import types

from agent.providers.base import CompletionResult, Provider, ToolCall, ToolDef


class GoogleProvider(Provider):
    name = "google"

    def __init__(self):
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)

    def complete(
        self,
        messages: list[dict],
        tools: list[ToolDef],
        model: str,
        system: str = "",
        max_tokens: int = 4096,
    ) -> CompletionResult:
        contents = self._convert_messages(messages)
        api_tools = self.convert_tools(tools)

        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
        )
        if system:
            config.system_instruction = system
        if api_tools:
            config.tools = api_tools

        response = self.client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        content = ""
        tool_calls = []

        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.text:
                    content += part.text
                elif part.function_call:
                    fc = part.function_call
                    tool_calls.append(ToolCall(
                        id=f"call_{uuid.uuid4().hex[:12]}",
                        name=fc.name,
                        arguments=dict(fc.args) if fc.args else {},
                    ))

        stop = "tool_use" if tool_calls else "end_turn"
        if response.candidates and response.candidates[0].finish_reason:
            fr = str(response.candidates[0].finish_reason)
            if "MAX_TOKENS" in fr:
                stop = "max_tokens"

        input_tokens = 0
        output_tokens = 0
        if response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0

        return CompletionResult(
            content=content,
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            stop_reason=stop,
        )

    def convert_tools(self, tools: list[ToolDef]) -> list[types.Tool]:
        declarations = []
        for t in tools:
            # Convert JSON schema to Gemini-compatible schema
            params = _jsonschema_to_gemini(t.parameters)
            declarations.append(types.FunctionDeclaration(
                name=t.name,
                description=t.description,
                parameters=params,
            ))
        return [types.Tool(function_declarations=declarations)]

    def _convert_messages(self, messages: list[dict]) -> list[types.Content]:
        """Convert internal message format to Gemini's format."""
        result = []
        for msg in messages:
            role = msg["role"]

            if role == "user":
                result.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=msg["content"])],
                ))

            elif role == "assistant":
                parts = []
                if msg.get("content"):
                    parts.append(types.Part.from_text(text=msg["content"]))
                for tc in msg.get("tool_calls") or []:
                    parts.append(types.Part.from_function_call(
                        name=tc.name,
                        args=tc.arguments,
                    ))
                result.append(types.Content(role="model", parts=parts))

            elif role == "tool_result":
                part = types.Part.from_function_response(
                    name=msg.get("name", "unknown"),
                    response={"result": msg["content"]},
                )
                # Batch consecutive tool results into one user turn
                if result and result[-1].role == "user" and any(
                    p.function_response for p in result[-1].parts
                ):
                    result[-1].parts.append(part)
                else:
                    result.append(types.Content(role="user", parts=[part]))

        return result


def _jsonschema_to_gemini(schema: dict) -> dict:
    """Convert a JSON Schema dict to a Gemini-compatible schema dict.

    Gemini's schema format is close to JSON Schema but has some differences.
    This does a best-effort conversion.
    """
    result = {}
    if "type" in schema:
        result["type"] = schema["type"].upper()
    if "properties" in schema:
        result["properties"] = {
            k: _jsonschema_to_gemini(v) for k, v in schema["properties"].items()
        }
    if "required" in schema:
        result["required"] = schema["required"]
    if "description" in schema:
        result["description"] = schema["description"]
    if "items" in schema:
        result["items"] = _jsonschema_to_gemini(schema["items"])
    if "enum" in schema:
        result["enum"] = schema["enum"]
    return result
