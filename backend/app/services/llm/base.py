from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        pass

    @abstractmethod
    async def generate_stream(
        self, prompt: str, system_prompt: str | None = None, **kwargs
    ) -> AsyncIterator[str]:
        pass

    @abstractmethod
    async def generate_with_context(
        self, 
        prompt: str, 
        context: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs
    ) -> str:
        pass
