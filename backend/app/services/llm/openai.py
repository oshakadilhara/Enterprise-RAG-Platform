"""OpenAI LLM provider."""

from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from app.core.config import Settings
from app.core.telemetry import TOKEN_USAGE
from app.domain.interfaces.llm import LLMProvider, LLMResponse


class OpenAILLMProvider(LLMProvider):
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model

    async def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature or self._settings.llm_temperature,
            max_tokens=max_tokens or self._settings.llm_max_tokens,
        )
        usage = response.usage
        if usage:
            TOKEN_USAGE.labels(provider="openai", type="input").inc(usage.prompt_tokens)
            TOKEN_USAGE.labels(provider="openai", type="output").inc(usage.completion_tokens)

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            tokens_input=usage.prompt_tokens if usage else 0,
            tokens_output=usage.completion_tokens if usage else 0,
            finish_reason=choice.finish_reason,
        )

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature or self._settings.llm_temperature,
            max_tokens=max_tokens or self._settings.llm_max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    @property
    def model_name(self) -> str:
        return self._model
