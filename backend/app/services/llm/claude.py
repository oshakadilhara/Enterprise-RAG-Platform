"""Anthropic Claude LLM provider."""

from collections.abc import AsyncGenerator

import anthropic

from app.core.config import Settings
from app.core.telemetry import TOKEN_USAGE
from app.domain.interfaces.llm import LLMProvider, LLMResponse


class ClaudeProvider(LLMProvider):
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.llm_model

    def _convert_messages(self, messages: list[dict[str, str]]) -> tuple[str | None, list[dict]]:
        system = None
        converted = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                converted.append({"role": msg["role"], "content": msg["content"]})
        return system, converted

    async def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system, converted = self._convert_messages(messages)
        response = await self._client.messages.create(
            model=self._model,
            system=system or "",
            messages=converted,
            temperature=temperature or self._settings.llm_temperature,
            max_tokens=max_tokens or self._settings.llm_max_tokens,
        )
        TOKEN_USAGE.labels(provider="claude", type="input").inc(response.usage.input_tokens)
        TOKEN_USAGE.labels(provider="claude", type="output").inc(response.usage.output_tokens)
        content = "".join(block.text for block in response.content if hasattr(block, "text"))
        return LLMResponse(
            content=content,
            model=self._model,
            tokens_input=response.usage.input_tokens,
            tokens_output=response.usage.output_tokens,
        )

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        system, converted = self._convert_messages(messages)
        async with self._client.messages.stream(
            model=self._model,
            system=system or "",
            messages=converted,
            temperature=temperature or self._settings.llm_temperature,
            max_tokens=max_tokens or self._settings.llm_max_tokens,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    @property
    def model_name(self) -> str:
        return self._model
