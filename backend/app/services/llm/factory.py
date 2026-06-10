"""LLM provider factory."""

from app.core.config import Settings
from app.domain.interfaces.llm import LLMProvider
from app.services.llm.claude import ClaudeProvider
from app.services.llm.gemini import GeminiLLMProvider
from app.services.llm.ollama import OllamaProvider
from app.services.llm.openai import OpenAILLMProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    providers = {
        "openai": OpenAILLMProvider,
        "gemini": GeminiLLMProvider,
        "claude": ClaudeProvider,
        "ollama": OllamaProvider,
    }
    provider_class = providers.get(settings.llm_provider)
    if not provider_class:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
    return provider_class(settings)
