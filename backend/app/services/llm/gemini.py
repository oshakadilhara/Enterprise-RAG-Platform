"""Google Gemini LLM provider."""

from collections.abc import AsyncGenerator

import google.generativeai as genai

from app.core.config import Settings
from app.domain.interfaces.llm import LLMProvider, LLMResponse


class GeminiLLMProvider(LLMProvider):
    def __init__(self, settings: Settings):
        self._settings = settings
        genai.configure(api_key=settings.google_api_key)
        self._model = genai.GenerativeModel(settings.llm_model)

    async def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        prompt = self._format_messages(messages)
        response = await self._model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=temperature or self._settings.llm_temperature,
                max_output_tokens=max_tokens or self._settings.llm_max_tokens,
            ),
        )
        return LLMResponse(
            content=response.text,
            model=self._settings.llm_model,
            tokens_input=0,
            tokens_output=0,
        )

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        prompt = self._format_messages(messages)
        response = await self._model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=temperature or self._settings.llm_temperature,
                max_output_tokens=max_tokens or self._settings.llm_max_tokens,
            ),
            stream=True,
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text

    def _format_messages(self, messages: list[dict[str, str]]) -> str:
        parts = []
        for msg in messages:
            parts.append(f"{msg['role'].upper()}: {msg['content']}")
        return "\n\n".join(parts)

    @property
    def model_name(self) -> str:
        return self._settings.llm_model
