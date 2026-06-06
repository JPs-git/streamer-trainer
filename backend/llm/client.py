from __future__ import annotations
import logging
from typing import Any, Optional

logger = logging.getLogger("llm")


class LLMClient:
    def __init__(
        self,
        provider: str = "openai",
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        selector_model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 150,
        timeout: float = 10.0,
    ):
        if api_key is None:
            raise ValueError("API key is required")
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.selector_model = selector_model or model
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._client = self._build_client()

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        if hasattr(self._client, "aclose"):
            await self._client.aclose()

    def _build_client(self) -> Any:
        if self.provider == "openai":
            from openai import AsyncOpenAI
            kwargs: dict[str, Any] = {"api_key": self.api_key, "timeout": self.timeout}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            return AsyncOpenAI(**kwargs)
        elif self.provider == "anthropic":
            from anthropic import AsyncAnthropic
            return AsyncAnthropic(api_key=self.api_key, timeout=self.timeout)
        raise ValueError(f"Unsupported provider: {self.provider}")

    async def chat(self, system: str, user: str, model: Optional[str] = None) -> str:
        model_name = model or self.model
        logger.debug("=== LLM Request [%s] ===", model_name)
        logger.debug("System:\n%s", system)
        logger.debug("User:\n%s", user)
        if self.provider == "openai":
            resp = await self._client.chat.completions.create(
                model=model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            content = resp.choices[0].message.content or ""
            logger.debug("Response:\n%s", content)
            logger.debug("=== LLM End ===")
            return content
        elif self.provider == "anthropic":
            resp = await self._client.messages.create(
                model=model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            content = resp.content[0].text if resp.content else ""
            logger.debug("Response:\n%s", content)
            logger.debug("=== LLM End ===")
            return content
        raise ValueError(f"Unsupported provider: {self.provider}")
