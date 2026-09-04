"""
LLM client using LiteLLM with provider fallback.
"""

from dataclasses import dataclass
from enum import Enum
import inspect
import os
import re
from typing import TYPE_CHECKING, Any

try:
    import litellm
except ImportError:  # pragma: no cover
    class _LiteLLMStub:
        class AuthenticationError(Exception):
            pass

        class RateLimitError(Exception):
            pass

        class ContextWindowExceededError(Exception):
            pass

        telemetry = False
        request_timeout = 30
        openai_api_key = None
        openrouter_api_key = None

        async def acompletion(self, *args, **kwargs):
            raise RuntimeError("litellm is not installed")

    litellm = _LiteLLMStub()

from tg_agent.logging import get_logger

if TYPE_CHECKING:
    from tg_agent.config import Settings
else:
    Settings = Any

logger = get_logger(__name__)


def _get_litellm_exception(name: str) -> tuple[type[BaseException], ...]:
    candidate = getattr(litellm, name, None)
    if isinstance(candidate, type) and issubclass(candidate, BaseException):
        return (candidate,)
    return ()


class LLMProvider(str, Enum):
    CHATGPT_OAUTH = "chatgpt_oauth"
    OPENAI = "openai"
    OPENROUTER = "openrouter"


@dataclass
class LLMResponse:
    content: str
    provider: LLMProvider
    model: str
    success: bool
    error_message: str | None = None


class LLMClient:
    """Provider-neutral LiteLLM client with deterministic fallback order."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.primary_provider = self._determine_primary_provider()
        self.fallback_chain = self._build_fallback_chain()
        self._configure_litellm()

    def _determine_primary_provider(self) -> LLMProvider:
        provider = self.settings.llm_provider
        if provider == "chatgpt_oauth" and self.settings.litellm_chatgpt_enabled:
            return LLMProvider.CHATGPT_OAUTH
        if provider == "openai" and self.settings.openai_api_key:
            return LLMProvider.OPENAI
        if provider == "openrouter" and self.settings.openrouter_api_key:
            return LLMProvider.OPENROUTER

        if self.settings.openai_api_key:
            return LLMProvider.OPENAI
        if self.settings.openrouter_api_key:
            return LLMProvider.OPENROUTER
        return LLMProvider.CHATGPT_OAUTH

    def _build_fallback_chain(self) -> list[LLMProvider]:
        candidates: list[LLMProvider] = []
        if self.settings.openai_api_key:
            candidates.append(LLMProvider.OPENAI)
        if self.settings.openrouter_api_key:
            candidates.append(LLMProvider.OPENROUTER)
        return [p for p in candidates if p != self.primary_provider]

    def _configure_litellm(self) -> None:
        if self.settings.litellm_chatgpt_enabled:
            token_dir = self.settings.chatgpt_token_dir_path
            try:
                token_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.error(
                    f"Failed to create ChatGPT token directory at {token_dir}: {exc}"
                )
                raise RuntimeError(
                    f"Failed to create ChatGPT token directory at {token_dir}"
                ) from exc
            os.environ["CHATGPT_TOKEN_DIR"] = str(token_dir)
            os.environ["CHATGPT_AUTH_FILE"] = self.settings.chatgpt_auth_file
            os.environ["CHATGPT_API_BASE"] = self.settings.chatgpt_api_base
            os.environ["CHATGPT_ORIGINATOR"] = self.settings.chatgpt_originator

        if self.settings.openai_api_key:
            litellm.openai_api_key = self.settings.openai_api_key
        if api_base := str(self.settings.openai_api_base or ""):
            os.environ["OPENAI_API_BASE"] = api_base
        if self.settings.openrouter_api_key:
            litellm.openrouter_api_key = self.settings.openrouter_api_key

        litellm.request_timeout = 120
        litellm.telemetry = False

    def _get_model_for_provider(self, provider: LLMProvider) -> str:
        if provider == LLMProvider.CHATGPT_OAUTH:
            return self.settings.llm_model
        if provider == LLMProvider.OPENAI:
            return self.settings.openai_fallback_model
        if provider == LLMProvider.OPENROUTER:
            return self.settings.openrouter_fallback_model
        return self.settings.llm_model

    def _get_provider_config(self, provider: LLMProvider) -> dict[str, Any]:
        config: dict[str, Any] = {}
        if provider == LLMProvider.CHATGPT_OAUTH:
            config["model"] = self.settings.llm_model
            config["max_tokens"] = min(self.settings.max_reply_chars, 1000)
        elif provider == LLMProvider.OPENAI:
            config["model"] = self.settings.openai_fallback_model
            config["temperature"] = 0.2
            config["top_p"] = 0.8
            config["max_tokens"] = 120
            if self.settings.openai_api_base:
                config["api_base"] = self.settings.openai_api_base
        elif provider == LLMProvider.OPENROUTER:
            config["model"] = self.settings.openrouter_fallback_model
            config["temperature"] = 0.7
            config["max_tokens"] = min(self.settings.max_reply_chars, 1000)
            config["headers"] = {
                "HTTP-Referer": "https://github.com/telegram-ai-userbot-agent",
                "X-Title": "Telegram AI Userbot Agent",
            }
        return config

    async def generate_reply(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> LLMResponse:
        """Generate text using primary provider and configured fallbacks."""
        full_messages = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        providers_to_try = [self.primary_provider, *self.fallback_chain]
        last_failure: LLMResponse | None = None

        for provider in providers_to_try:
            try:
                logger.info(f"Attempting LLM generation with {provider.value}")
                response = await self._generate_with_provider(provider, full_messages)
                if response.success:
                    logger.info(
                        f"Successfully generated reply using {provider.value}"
                    )
                    return response
                logger.warning(
                    f"Provider {provider.value} failed: {response.error_message}"
                )
                last_failure = response
            except Exception as exc:
                logger.error(f"Provider {provider.value} error: {exc}")

        error_msg = "All LLM providers failed"
        if last_failure and last_failure.error_message:
            error_msg = f"{error_msg}: {last_failure.error_message}"
        logger.error(error_msg)
        return LLMResponse(
            content="",
            provider=self.primary_provider,
            model=self.settings.llm_model,
            success=False,
            error_message=error_msg,
        )

    async def _generate_with_provider(
        self,
        provider: LLMProvider,
        messages: list[dict[str, str]],
    ) -> LLMResponse:
        import asyncio

        config = self._get_provider_config(provider)
        model = config.pop("model")

        try:
            completion_result = litellm.acompletion(
                model=model,
                messages=messages,
                **config,
            )
            if inspect.isawaitable(completion_result):
                response = await asyncio.wait_for(completion_result, timeout=90.0)
            else:
                response = completion_result

            usage = getattr(response, "usage", None)
            if usage:
                completion_tokens = getattr(usage, "completion_tokens", "?")
                details = getattr(usage, "completion_tokens_details", None)
                reasoning_tokens = (
                    getattr(details, "reasoning_tokens", 0) if details else 0
                )
                logger.info(
                    f"Tokens: reasoning={reasoning_tokens}, "
                    f"completion={completion_tokens}"
                )

            message = response.choices[0].message
            content = getattr(message, "content", None)
            if not isinstance(content, str) or not content.strip():
                # Never promote hidden/internal reasoning to a user-visible reply.
                return LLMResponse(
                    content="",
                    provider=provider,
                    model=model,
                    success=False,
                    error_message="Empty response from LLM",
                )

            content = re.sub(
                r"<think>.*?</think>",
                "",
                content,
                flags=re.DOTALL | re.IGNORECASE,
            ).strip()
            if not content:
                return LLMResponse(
                    content="",
                    provider=provider,
                    model=model,
                    success=False,
                    error_message="LLM returned no usable reply",
                )

            if len(content) > self.settings.max_reply_chars:
                content = content[: self.settings.max_reply_chars - 3] + "..."

            logger.debug(
                f"LLM reply generated: provider={provider.value}, chars={len(content)}"
            )
            return LLMResponse(
                content=content,
                provider=provider,
                model=model,
                success=True,
            )

        except _get_litellm_exception("AuthenticationError") as exc:
            return LLMResponse(
                content="",
                provider=provider,
                model=model,
                success=False,
                error_message=f"Authentication error: {exc}",
            )
        except _get_litellm_exception("RateLimitError") as exc:
            return LLMResponse(
                content="",
                provider=provider,
                model=model,
                success=False,
                error_message=f"Rate limit exceeded: {exc}",
            )
        except _get_litellm_exception("ContextWindowExceededError") as exc:
            return LLMResponse(
                content="",
                provider=provider,
                model=model,
                success=False,
                error_message=f"Context too long: {exc}",
            )
        except asyncio.TimeoutError:
            logger.error(f"LLM request timed out after 90s ({provider.value})")
            return LLMResponse(
                content="",
                provider=provider,
                model=model,
                success=False,
                error_message="LLM request timed out (90s)",
            )
        except Exception as exc:
            return LLMResponse(
                content="",
                provider=provider,
                model=model,
                success=False,
                error_message=str(exc),
            )

    def get_status(self) -> dict[str, Any]:
        return {
            "primary_provider": self.primary_provider.value,
            "primary_model": self.settings.llm_model,
            "fallback_providers": [p.value for p in self.fallback_chain],
            "chatgpt_oauth_enabled": self.settings.litellm_chatgpt_enabled,
            "chatgpt_token_dir": str(self.settings.chatgpt_token_dir_path),
            "chatgpt_auth_file": str(self.settings.chatgpt_auth_file_path),
            "openai_configured": bool(self.settings.openai_api_key),
            "openrouter_configured": bool(self.settings.openrouter_api_key),
        }

    async def smoke_test(self) -> LLMResponse:
        return await self.generate_reply(
            messages=[{"role": "user", "content": "привет"}],
            system_prompt="Отвечай одним словом.",
        )
