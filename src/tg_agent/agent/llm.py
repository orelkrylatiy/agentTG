"""
LLM client using LiteLLM with provider fallback.
"""

from dataclasses import dataclass
from enum import Enum
import inspect
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
    """Supported LLM providers."""

    CHATGPT_OAUTH = "chatgpt_oauth"
    OPENAI = "openai"
    OPENROUTER = "openrouter"


@dataclass
class LLMResponse:
    """Response from LLM generation."""

    content: str
    provider: LLMProvider
    model: str
    success: bool
    error_message: str | None = None


class LLMClient:
    """
    LLM client with provider fallback using LiteLLM.

    Supports:
    - chatgpt_oauth: ChatGPT Plus subscription via LiteLLM OAuth
    - openai: Direct OpenAI API
    - openrouter: OpenRouter API with multiple models
    """

    def __init__(self, settings: Settings):
        """
        Initialize LLM client.

        Args:
            settings: Application settings.
        """
        self.settings = settings
        self.primary_provider = self._determine_primary_provider()
        self.fallback_chain = self._build_fallback_chain()

        # Configure LiteLLM
        self._configure_litellm()

    def _determine_primary_provider(self) -> LLMProvider:
        """Determine primary provider from settings."""
        provider = self.settings.llm_provider

        if provider == "chatgpt_oauth" and self.settings.litellm_chatgpt_enabled:
            return LLMProvider.CHATGPT_OAUTH
        elif provider == "openai" and self.settings.openai_api_key:
            return LLMProvider.OPENAI
        elif provider == "openrouter" and self.settings.openrouter_api_key:
            return LLMProvider.OPENROUTER

        # Default fallback
        if self.settings.openai_api_key:
            return LLMProvider.OPENAI
        elif self.settings.openrouter_api_key:
            return LLMProvider.OPENROUTER

        return LLMProvider.CHATGPT_OAUTH

    def _build_fallback_chain(self) -> list[LLMProvider]:
        """Build fallback provider chain."""
        chain = []

        # Add configured fallbacks in order
        if self.settings.openai_api_key:
            chain.append(LLMProvider.OPENAI)

        if self.settings.openrouter_api_key:
            chain.append(LLMProvider.OPENROUTER)

        return chain

    def _configure_litellm(self) -> None:
        """Configure LiteLLM with API keys."""
        # OpenAI
        if self.settings.openai_api_key:
            litellm.openai_api_key = self.settings.openai_api_key

        # OpenRouter
        if self.settings.openrouter_api_key:
            litellm.openrouter_api_key = self.settings.openrouter_api_key

        # ChatGPT OAuth doesn't need a key - uses device code flow
        # User must run litellm authentication separately

        # Set default timeout
        litellm.request_timeout = 30

        # Disable telemetry
        litellm.telemetry = False

    def _get_model_for_provider(self, provider: LLMProvider) -> str:
        """Get model name for a provider."""
        if provider == LLMProvider.CHATGPT_OAUTH:
            return self.settings.llm_model
        elif provider == LLMProvider.OPENAI:
            return self.settings.openai_fallback_model
        elif provider == LLMProvider.OPENROUTER:
            return self.settings.openrouter_fallback_model
        return self.settings.llm_model

    def _get_provider_config(self, provider: LLMProvider) -> dict[str, Any]:
        """Get provider-specific configuration."""
        config: dict[str, Any] = {}

        if provider == LLMProvider.CHATGPT_OAUTH:
            # ChatGPT OAuth via LiteLLM
            # Model format: "chatgpt/<model-name>"
            config["model"] = self.settings.llm_model
            # Don't pass temperature or other params that might not be supported
            config["max_tokens"] = min(self.settings.max_reply_chars, 1000)

        elif provider == LLMProvider.OPENAI:
            config["model"] = self.settings.openai_fallback_model
            config["temperature"] = 0.7
            config["max_tokens"] = min(self.settings.max_reply_chars, 1000)

        elif provider == LLMProvider.OPENROUTER:
            config["model"] = self.settings.openrouter_fallback_model
            config["temperature"] = 0.7
            config["max_tokens"] = min(self.settings.max_reply_chars, 1000)
            # OpenRouter specific headers
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
        """
        Generate a reply using the LLM with fallback.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            system_prompt: System prompt for the conversation.

        Returns:
            LLMResponse with generated content.
        """
        # Build full message list with system prompt
        full_messages = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        # Try primary provider first
        providers_to_try = [self.primary_provider] + self.fallback_chain
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

            except Exception as e:
                logger.error(f"Provider {provider.value} error: {e}")
                continue

        # All providers failed
        error_msg = "All LLM providers failed"
        if last_failure and last_failure.error_message:
            error_msg = f"{error_msg}: {last_failure.error_message}"
        logger.error(error_msg)

        return LLMResponse(
            content=f"[Error: {error_msg}. Please check LLM configuration.]",
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
        """
        Generate response using a specific provider.

        Args:
            provider: Provider to use.
            messages: Full message list including system prompt.

        Returns:
            LLMResponse with generated content.
        """
        config = self._get_provider_config(provider)
        model = config.pop("model")

        try:
            completion_result = litellm.acompletion(
                model=model,
                messages=messages,
                **config,
            )
            response = (
                await completion_result
                if inspect.isawaitable(completion_result)
                else completion_result
            )

            content = response.choices[0].message.content

            if content is None:
                return LLMResponse(
                    content="",
                    provider=provider,
                    model=model,
                    success=False,
                    error_message="Empty response from LLM",
                )

            # Truncate if too long
            if len(content) > self.settings.max_reply_chars:
                content = content[: self.settings.max_reply_chars - 3] + "..."

            return LLMResponse(
                content=content,
                provider=provider,
                model=model,
                success=True,
            )

        except _get_litellm_exception("AuthenticationError") as e:
            return LLMResponse(
                content="",
                provider=provider,
                model=model,
                success=False,
                error_message=f"Authentication error: {e}",
            )

        except _get_litellm_exception("RateLimitError") as e:
            return LLMResponse(
                content="",
                provider=provider,
                model=model,
                success=False,
                error_message=f"Rate limit exceeded: {e}",
            )

        except _get_litellm_exception("ContextWindowExceededError") as e:
            return LLMResponse(
                content="",
                provider=provider,
                model=model,
                success=False,
                error_message=f"Context too long: {e}",
            )

        except Exception as e:
            return LLMResponse(
                content="",
                provider=provider,
                model=model,
                success=False,
                error_message=str(e),
            )

    def get_status(self) -> dict[str, Any]:
        """Get current LLM client status."""
        return {
            "primary_provider": self.primary_provider.value,
            "primary_model": self.settings.llm_model,
            "fallback_providers": [p.value for p in self.fallback_chain],
            "chatgpt_oauth_enabled": self.settings.litellm_chatgpt_enabled,
            "openai_configured": bool(self.settings.openai_api_key),
            "openrouter_configured": bool(self.settings.openrouter_api_key),
        }
