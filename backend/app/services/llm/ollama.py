"""Ollama local LLM provider."""

from collections.abc import AsyncGenerator

import httpx

from app.core.config import Settings
from app.domain.interfaces.llm import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    def __init__(self, settings: Settings):
        self._settings = settings
        self._base_url = settings.ollama_base_url
        self._model = settings.llm_model

    async def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature or self._settings.llm_temperature,
                        "num_predict": max_tokens or self._settings.llm_max_tokens,
                    },
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()
            return LLMResponse(
                content=data["message"]["content"],
                model=self._model,
                tokens_input=data.get("prompt_eval_count", 0),
                tokens_output=data.get("eval_count", 0),
            )

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": temperature or self._settings.llm_temperature,
                        "num_predict": max_tokens or self._settings.llm_max_tokens,
                    },
                },
                timeout=120.0,
            ) as response:
                response.raise_for_status()
                import json
                async for line in response.aiter_lines():
                    if line:
                        data = json.loads(line)
                        if content := data.get("message", {}).get("content"):
                            yield content

    @property
    def model_name(self) -> str:
        return self._model
