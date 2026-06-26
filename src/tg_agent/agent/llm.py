"""
LLM client using LiteLLM with provider fallback.
"""

from dataclasses import dataclass
from enum import Enum
import inspect
import os
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
        if self.settings.litellm_chatgpt_enabled:
            token_dir = self.settings.chatgpt_token_dir_path
            try:
                token_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.error(f"Failed to create ChatGPT token directory at {token_dir}: {exc}")
                raise RuntimeError(
                    f"Failed to create ChatGPT token directory at {token_dir}"
                ) from exc
            os.environ["CHATGPT_TOKEN_DIR"] = str(token_dir)
            os.environ["CHATGPT_AUTH_FILE"] = self.settings.chatgpt_auth_file
            os.environ["CHATGPT_API_BASE"] = self.settings.chatgpt_api_base
            os.environ["CHATGPT_ORIGINATOR"] = self.settings.chatgpt_originator

        # OpenAI (also covers LM Studio / local OpenAI-compatible servers)
        if self.settings.openai_api_key:
            litellm.openai_api_key = self.settings.openai_api_key
        if api_base := str(self.settings.openai_api_base or ""):
            os.environ["OPENAI_API_BASE"] = api_base

        # OpenRouter
        if self.settings.openrouter_api_key:
            litellm.openrouter_api_key = self.settings.openrouter_api_key

        # ChatGPT OAuth doesn't need a key - uses device code flow
        # User must run litellm authentication separately

        # Set default timeout — qwen3 thinking mode can be slow
        litellm.request_timeout = 120

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
            config["temperature"] = 0.15
            config["top_p"] = 0.7
            config["max_tokens"] = 600
            if self.settings.openai_api_base:
                config["api_base"] = self.settings.openai_api_base
            # This model ignores enable_thinking=False — it always reasons.
            # With True, reasoning goes to reasoning_content (clean separation).
            # max_tokens=600: ~440 for reasoning + ~120 for actual reply.
            config["extra_body"] = {"enable_thinking": True}

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
        # Build full message list with system prompt.
        # Prepend /no_think to the first user message — qwen3-specific token
        # that disables the internal thinking phase for that turn.
        # Patch /no_think into first AND last user messages
        patched = list(messages)
        first_idx = next((i for i, m in enumerate(patched) if m["role"] == "user"), None)
        last_idx = next((i for i, m in enumerate(reversed(patched)) if m["role"] == "user"), None)
        if last_idx is not None:
            last_idx = len(patched) - 1 - last_idx
        for idx in {first_idx, last_idx}:
            if idx is not None:
                m = patched[idx]
                if not m["content"].startswith("/no_think"):
                    patched[idx] = {**m, "content": "/no_think\n" + m["content"]}

        full_messages = [
            {"role": "system", "content": system_prompt},
            *patched,
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
        oauth_context = (
            f" token_dir={self.settings.chatgpt_token_dir_path}"
            f" api_base={self.settings.chatgpt_api_base}"
        )

        try:
            import asyncio as _asyncio
            completion_result = litellm.acompletion(
                model=model,
                messages=messages,
                **config,
            )
            coro = completion_result if inspect.isawaitable(completion_result) else None
            if coro:
                response = await _asyncio.wait_for(coro, timeout=90.0)
            else:
                response = completion_result

            # Log token breakdown
            usage = getattr(response, "usage", None)
            if usage:
                total = getattr(usage, "completion_tokens", "?")
                details = getattr(usage, "completion_tokens_details", None)
                reasoning = getattr(details, "reasoning_tokens", 0) if details else 0
                logger.info(f"Tokens: reasoning={reasoning}, completion={total}")

            content = response.choices[0].message.content

            if not content:
                rc = getattr(response.choices[0].message, "reasoning_content", None)
                if rc:
                    content = rc
                else:
                    return LLMResponse(
                        content="",
                        provider=provider,
                        model=model,
                        success=False,
                        error_message="Empty response from LLM",
                    )


            import re as _re
            raw_content = content
            logger.info(f"Raw LLM content: {raw_content!r}")

            # With enable_thinking=True, reasoning goes to reasoning_content and
            # content holds only the clean reply — just strip whitespace.
            content = _re.sub(r"<think>.*?</think>", "", content, flags=_re.DOTALL).strip()

            # Safety net in case thinking leaked into content anyway
            # Matches: "Thinking Process:", "Here's a thinking process:", "**Analyze", "1.  **"
            if content and _re.match(
                r"^(Thinking Process:|Here'?s? (a )?thinking process:|\*{1,2}Analyze|\d+\.\s+\*{1,2})",
                content
            ):
                logger.warning("Thinking leaked into content; extracting quoted phrase")
                extracted = ""

                # 1. Look for "[Output Generation] -> "text"" pattern (most reliable)
                m = _re.search(
                    r'\[Output Generation\]\s*->\s*["\u201c\u00ab]([\u0410-\u044f\u0401\u0451][^"\u201d\u00bb\n]{10,300})["\u201d\u00bb]',
                    raw_content
                )
                if m:
                    extracted = m.group(1).strip()
                    logger.info(f"[Output Generation] extraction: {extracted!r}")

                # 2. Look for "Final Output/Text:" followed by the reply
                if not extracted:
                    m = _re.search(
                        r'Final (?:Output|Text)[^:]*:\s*\n?\s*([^\n*#]{20,300})',
                        raw_content
                    )
                    if m:
                        candidate = m.group(1).strip().strip('"').strip('\u201c').strip('\u201d')
                        if candidate and not candidate.startswith(('*', '#', '(')):
                            extracted = candidate
                            logger.info(f"Final Output/Text extraction: {extracted!r}")

                # 3. Look for an unquoted line starting with a greeting
                if not extracted:
                    for line in reversed(raw_content.split('\n')):
                        line = line.strip().strip('*').strip()
                        if (_re.match(r'^(\u041f\u0440\u0438\u0432\u0435\u0442|\u0417\u0434\u0440\u0430\u0432\u0441\u0442\u0432\u0443\u0439\u0442\u0435|\u0414\u043e\u0431\u0440\u044b\u0439)', line)
                                and len(line) >= 30):
                            extracted = line.strip('"').strip('\u201c').strip('\u201d')
                            logger.info(f"Greeting-line extraction: {extracted!r}")
                            break

                # 4. Quoted phrase fallback \u2014 allow up to 250 chars
                if not extracted:
                    quoted = _re.findall(
                        r'["\u201c\u201d\u00ab]([\u0410-\u044f\u0401\u0451a-zA-Z][^"\u201c\u201d\u00bb\n]{10,250})["\u201c\u201d\u00bb]',
                        raw_content
                    )
                    _SKIP = ('\u043f\u0438\u0448\u0438 ', '\u043d\u0435 ', '\u0431\u0435\u0437 ',
                             '\u043d\u0438\u043a\u043e\u0433\u0434\u0430', '\u0442\u043e\u043b\u044c\u043a\u043e ',
                             '\u0441\u0442\u0438\u043b\u044c', '\u043e\u0442\u0432\u0435\u0442', '\u0442\u0435\u043a\u0441\u0442',
                             '\u043f\u0440\u0430\u0432\u0438\u043b', '\u043f\u0440\u0438\u043c\u0435\u0440',
                             'write ', 'output ', 'never ', 'only ', 'just ', 'lively', 'short')
                    reply_candidates = [
                        p for p in quoted
                        if not p.lower().startswith(_SKIP)
                        and sum(1 for c in p if '\u0410' <= c <= '\u044f' or c in '\u0401\u0451') >= 5
                    ]
                    if reply_candidates:
                        extracted = reply_candidates[-1].strip()
                        logger.info(f"Quoted-phrase extraction: {extracted!r}")

                content = extracted
            if not content:
                logger.warning(f"Empty reply. Raw: {raw_content!r}")
                return LLMResponse(
                    content="",
                    provider=provider,
                    model=model,
                    success=False,
                    error_message="LLM returned no usable reply",
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
                error_message=f"Authentication error: {e}.{oauth_context}",
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

        except _asyncio.TimeoutError:
            logger.error(f"LLM request timed out after 90s ({provider.value})")
            return LLMResponse(
                content="",
                provider=provider,
                model=model,
                success=False,
                error_message="LLM request timed out (90s)",
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
            "chatgpt_token_dir": str(self.settings.chatgpt_token_dir_path),
            "chatgpt_auth_file": str(self.settings.chatgpt_auth_file_path),
            "openai_configured": bool(self.settings.openai_api_key),
            "openrouter_configured": bool(self.settings.openrouter_api_key),
        }

    async def smoke_test(self) -> LLMResponse:
        """Run a minimal provider smoke test."""
        return await self.generate_reply(
            messages=[{"role": "user", "content": "привет"}],
            system_prompt="Отвечай одним словом.",
        )
