from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("llm")
_llm_trace = logging.getLogger("llm_trace")


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
        request_interval: float = 2.0,
        max_interval: float = 15.0,
        fallback_provider: str = "openai",
        fallback_api_key: Optional[str] = None,
        fallback_base_url: Optional[str] = None,
        fallback_model: str = "",
        fallback_timeout: float = 15.0,
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
        self.request_interval = request_interval
        self.max_interval = max_interval
        self._client = self._build_client(provider, api_key, base_url, timeout)

        self.fallback_model = fallback_model or model
        self._fallback_client: Any = None
        if fallback_api_key:
            self._fallback_client = self._build_client(
                fallback_provider, fallback_api_key, fallback_base_url, fallback_timeout,
            )

        self._lock = asyncio.Lock()
        self._last_request_time = 0.0
        self._current_interval = request_interval

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        if hasattr(self._client, "aclose"):
            await self._client.aclose()
        if self._fallback_client is not None and hasattr(self._fallback_client, "aclose"):
            await self._fallback_client.aclose()

    @staticmethod
    def _build_client(
        provider: str, api_key: str, base_url: Optional[str], timeout: float,
    ) -> Any:
        if provider == "openai":
            from openai import AsyncOpenAI
            kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout, "max_retries": 0}
            if base_url:
                kwargs["base_url"] = base_url
            return AsyncOpenAI(**kwargs)
        elif provider == "anthropic":
            from anthropic import AsyncAnthropic
            return AsyncAnthropic(api_key=api_key, timeout=timeout)
        raise ValueError(f"Unsupported provider: {provider}")

    async def _call_api(self, client: Any, model: str, system: str, user: str, **kwargs: Any) -> str:
        if self.provider == "openai":
            resp = await client.chat.completions.create(
                model=model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **kwargs,
            )
            return resp.choices[0].message.content or ""
        elif self.provider == "anthropic":
            resp = await client.messages.create(
                model=model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text if resp.content else ""
        raise ValueError(f"Unsupported provider: {self.provider}")

    async def chat(self, system: str, user: str, model: Optional[str] = None) -> Optional[str]:
        model_name = model or self.model
        logger.debug("=== LLM Request [%s] ===", model_name)
        logger.debug("System:\n%s", system)
        logger.debug("User:\n%s", user)

        primary_failed = False
        async with self._lock:
            now = time.monotonic()
            since_last = now - self._last_request_time
            if since_last < self._current_interval:
                await asyncio.sleep(self._current_interval - since_last)

            try:
                content = await self._call_api(self._client, model_name, system, user)
            except Exception as e:
                primary_failed = True
                rate_limited = "RateLimitError" in type(e).__name__
                timed_out = "Timeout" in type(e).__name__
                if (rate_limited or timed_out) and self._fallback_client is not None:
                    self._current_interval = min(self._current_interval * 1.5, self.max_interval)
                    logger.warning(
                        "Primary LLM failed (%s), trying fallback (interval=%.1fs)...",
                        "rate limited" if rate_limited else "timed out",
                        self._current_interval,
                    )
                    try:
                        kwargs = {}
                        if rate_limited:
                            kwargs["extra_body"] = {"reasoning": {"enabled": False}}
                        content = await self._call_api(
                            self._fallback_client, self.fallback_model, system, user, **kwargs,
                        )
                        logger.info("Fallback LLM succeeded")
                        primary_failed = False
                    except Exception as e2:
                        logger.warning(
                            "Fallback LLM also failed (%s: %s), skipping",
                            type(e2).__name__, e2,
                        )
                        return None
                else:
                    self._current_interval = min(self._current_interval * 1.5, self.max_interval)
                    logger.warning("LLM call failed (%s: %s), skipping", type(e).__name__, e)
                    return None
            finally:
                self._last_request_time = time.monotonic()

        if not primary_failed and self._current_interval > self.request_interval:
            self._current_interval = max(self._current_interval - 1.0, self.request_interval)
        logger.debug("Response:\n%s", content)
        logger.debug("=== LLM End ===")
        _llm_trace.debug(
            "=== Generator Call model=%s ===\n"
            "--- SYSTEM ---\n%s\n"
            "--- USER ---\n%s\n"
            "--- RESPONSE ---\n%s",
            model_name, system, user, content,
        )
        return content
