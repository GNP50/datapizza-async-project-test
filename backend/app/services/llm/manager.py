from app.core.config import get_settings
from .ollama_provider import OllamaProvider


class LLMManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        settings = get_settings()
        provider_type = getattr(settings, "llm_provider", "ollama").lower()

        if provider_type == "ollama":
            api_key = settings.ollama_api_key
            self.provider = OllamaProvider(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                api_key=api_key
            )
        else:
            raise ValueError(f"Unknown LLM provider: {provider_type}")

        self._initialized = True

    async def generate(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        return await self.provider.generate(prompt, system_prompt, **kwargs)

    async def generate_stream(self, prompt: str, system_prompt: str | None = None, **kwargs):
        async for chunk in self.provider.generate_stream(prompt, system_prompt, **kwargs):
            yield chunk

    async def generate_with_context(
        self,
        prompt: str,
        context: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs
    ) -> str:
        return await self.provider.generate_with_context(prompt, context, system_prompt, **kwargs)


llm_manager = LLMManager()
