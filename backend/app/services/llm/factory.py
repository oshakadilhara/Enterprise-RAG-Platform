"""LLM provider factory.

Provider modules are imported lazily so a deployment only needs the SDK of
the provider it actually configures.
"""

from app.core.config import Settings
from app.domain.interfaces.llm import LLMProvider


def create_llm_provider(settings: Settings, model_override: str | None = None) -> LLMProvider:
    if model_override:
        # Shallow copy so the override doesn't leak into the cached Settings
        settings = settings.model_copy(update={"llm_model": model_override})

    provider = settings.llm_provider

    if provider == "openai":
        from app.services.llm.openai import OpenAILLMProvider
        return OpenAILLMProvider(settings)
    if provider == "gemini":
        from app.services.llm.gemini import GeminiLLMProvider
        return GeminiLLMProvider(settings)
    if provider == "claude":
        from app.services.llm.claude import ClaudeProvider
        return ClaudeProvider(settings)
    if provider == "ollama":
        from app.services.llm.ollama import OllamaProvider
        return OllamaProvider(settings)

    raise ValueError(f"Unknown LLM provider: {provider}")


def create_utility_llm_provider(settings: Settings) -> LLMProvider:
    """Cheap model for internal calls (query expansion, classification).

    Cost Tier 1 — see docs/COST_OPTIMIZATION.md.
    """
    return create_llm_provider(settings, model_override=settings.llm_utility_model)
