from datapizza.core.clients.client import Client
from app.core.config import get_settings


def get_llm_client() -> Client:
    """
    Factory function to get the appropriate LLM client based on configuration.

    Returns the correct datapizza client based on LLM_PROVIDER setting:
    - ollama: OllamaDatapizzaClient (custom implementation)
    - openai: OpenAIClient
    - openai_like: OpenAILikeClient
    - anthropic: AnthropicClient
    - google: GoogleClient
    - mistral: MistralClient
    - etc.
    """
    settings = get_settings()
    provider = settings.llm_provider.lower()
    system_prompt = "You are a helpful AI assistant with fact-checking capabilities."

    if provider == "ollama":
        # Use custom OllamaDatapizzaClient for native Ollama API support
        from .ollama_datapizza_client import OllamaDatapizzaClient

        api_key = settings.ollama_api_key
        if not api_key:
            raise ValueError("OLLAMA_API_KEY is required when using ollama provider")

        return OllamaDatapizzaClient(
            api_key=api_key,
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            system_prompt=system_prompt
        )

    elif provider == "openai":
        # Use datapizza's native OpenAI client
        from datapizza.clients.openai import OpenAIClient

        api_key = getattr(settings, "openai_api_key", None)
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when using openai provider")

        return OpenAIClient(
            api_key=api_key,
            model=getattr(settings, "openai_model", "gpt-4"),
            system_prompt=system_prompt
        )

    elif provider == "openai_like":
        # Use OpenAILikeClient for OpenAI-compatible APIs
        from datapizza.clients.openai_like import OpenAILikeClient

        base_url = getattr(settings, "openai_like_base_url", f"{settings.ollama_base_url}/v1")
        api_key = getattr(settings, "openai_like_api_key", settings.ollama_api_key) or ""
        model = getattr(settings, "openai_like_model", settings.ollama_model)

        return OpenAILikeClient(
            api_key=api_key,
            model=model,
            base_url=base_url,
            system_prompt=system_prompt
        )

    elif provider == "anthropic":
        # Use datapizza's Anthropic client
        from datapizza.clients.anthropic import AnthropicClient

        api_key = getattr(settings, "anthropic_api_key", None)
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when using anthropic provider")

        return AnthropicClient(
            api_key=api_key,
            model=getattr(settings, "anthropic_model", "claude-3-5-sonnet-20241022"),
            system_prompt=system_prompt
        )

    elif provider == "google":
        # Use datapizza's Google client
        from datapizza.clients.google import GoogleClient

        api_key = getattr(settings, "google_api_key", None)
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is required when using google provider")

        return GoogleClient(
            api_key=api_key,
            model=getattr(settings, "google_model", "gemini-1.5-pro"),
            system_prompt=system_prompt
        )

    elif provider == "mistral":
        # Use datapizza's Mistral client
        from datapizza.clients.mistral import MistralClient

        api_key = getattr(settings, "mistral_api_key", None)
        if not api_key:
            raise ValueError("MISTRAL_API_KEY is required when using mistral provider")

        return MistralClient(
            api_key=api_key,
            model=getattr(settings, "mistral_model", "mistral-large-latest"),
            system_prompt=system_prompt
        )

    else:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            f"Supported providers: ollama, openai, openai_like, anthropic, google, mistral"
        )


llm_client = get_llm_client()
