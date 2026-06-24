"""
Tests for LLM provider selection and fallback.
"""

from unittest.mock import MagicMock, patch

import pytest

from tg_agent.agent.llm import LLMClient, LLMProvider, LLMResponse


class TestLLMProvider:
    """Tests for LLMProvider enum."""

    def test_provider_values(self):
        assert LLMProvider.CHATGPT_OAUTH.value == "chatgpt_oauth"
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.OPENROUTER.value == "openrouter"


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_successful_response(self):
        response = LLMResponse(
            content="Hello, world!",
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini",
            success=True,
        )
        assert response.content == "Hello, world!"
        assert response.success is True
        assert response.error_message is None

    def test_failed_response(self):
        response = LLMResponse(
            content="",
            provider=LLMProvider.CHATGPT_OAUTH,
            model="chatgpt/gpt-5",
            success=False,
            error_message="Authentication failed",
        )
        assert response.success is False
        assert response.error_message == "Authentication failed"


class TestLLMClientProviderSelection:
    """Tests for LLMClient provider selection logic."""

    @pytest.fixture
    def mock_settings_chatgpt(self):
        settings = MagicMock()
        settings.llm_provider = "chatgpt_oauth"
        settings.litellm_chatgpt_enabled = True
        settings.llm_model = "chatgpt/gpt-5"
        settings.openai_api_key = ""
        settings.openrouter_api_key = ""
        settings.openai_fallback_model = "gpt-4o-mini"
        settings.openrouter_fallback_model = "openrouter/openai/gpt-4o-mini"
        settings.max_reply_chars = 800
        return settings

    @pytest.fixture
    def mock_settings_openai(self):
        settings = MagicMock()
        settings.llm_provider = "openai"
        settings.litellm_chatgpt_enabled = False
        settings.llm_model = "chatgpt/gpt-5"
        settings.openai_api_key = "sk-test-key"
        settings.openrouter_api_key = ""
        settings.openai_fallback_model = "gpt-4o-mini"
        settings.openrouter_fallback_model = "openrouter/openai/gpt-4o-mini"
        settings.max_reply_chars = 800
        return settings

    @pytest.fixture
    def mock_settings_openrouter(self):
        settings = MagicMock()
        settings.llm_provider = "openrouter"
        settings.litellm_chatgpt_enabled = False
        settings.llm_model = "chatgpt/gpt-5"
        settings.openai_api_key = ""
        settings.openrouter_api_key = "sk-or-test-key"
        settings.openai_fallback_model = "gpt-4o-mini"
        settings.openrouter_fallback_model = "openrouter/openai/gpt-4o-mini"
        settings.max_reply_chars = 800
        return settings

    def test_primary_chatgpt(self, mock_settings_chatgpt):
        """Should select chatgpt_oauth as primary when enabled."""
        client = LLMClient(mock_settings_chatgpt)
        assert client.primary_provider == LLMProvider.CHATGPT_OAUTH

    def test_primary_openai(self, mock_settings_openai):
        """Should select openai as primary when configured."""
        client = LLMClient(mock_settings_openai)
        assert client.primary_provider == LLMProvider.OPENAI

    def test_primary_openrouter(self, mock_settings_openrouter):
        """Should select openrouter as primary when configured."""
        client = LLMClient(mock_settings_openrouter)
        assert client.primary_provider == LLMProvider.OPENROUTER

    def test_fallback_chain_openai(self, mock_settings_chatgpt):
        """Should have empty fallback chain when no keys configured."""
        client = LLMClient(mock_settings_chatgpt)
        assert len(client.fallback_chain) == 0

    def test_fallback_chain_with_keys(self, mock_settings_chatgpt):
        """Should build fallback chain when keys are configured."""
        mock_settings_chatgpt.openai_api_key = "sk-test"
        mock_settings_chatgpt.openrouter_api_key = "sk-or-test"

        client = LLMClient(mock_settings_chatgpt)
        assert LLMProvider.OPENAI in client.fallback_chain
        assert LLMProvider.OPENROUTER in client.fallback_chain

    def test_get_model_for_provider(self, mock_settings_openai):
        """Should return correct model for each provider."""
        client = LLMClient(mock_settings_openai)

        # For OpenAI provider
        model = client._get_model_for_provider(LLMProvider.OPENAI)
        assert model == "gpt-4o-mini"

    def test_get_status(self, mock_settings_chatgpt):
        """Should return correct status dict."""
        client = LLMClient(mock_settings_chatgpt)
        status = client.get_status()

        assert status["primary_provider"] == "chatgpt_oauth"
        assert status["primary_model"] == "chatgpt/gpt-5"
        assert status["chatgpt_oauth_enabled"] is True
        assert status["openai_configured"] is False
        assert status["openrouter_configured"] is False


class TestLLMClientProviderFallback:
    """Tests for LLMClient fallback behavior."""

    @pytest.fixture
    def mock_settings_all_providers(self):
        settings = MagicMock()
        settings.llm_provider = "chatgpt_oauth"
        settings.litellm_chatgpt_enabled = True
        settings.llm_model = "chatgpt/gpt-5"
        settings.openai_api_key = "sk-test"
        settings.openrouter_api_key = "sk-or-test"
        settings.openai_fallback_model = "gpt-4o-mini"
        settings.openrouter_fallback_model = "openrouter/openai/gpt-4o-mini"
        settings.max_reply_chars = 800
        return settings

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self, mock_settings_all_providers):
        """Should fallback to next provider when primary fails."""
        with patch('tg_agent.agent.llm.litellm') as mock_litellm:
            # Primary fails
            mock_litellm.acompletion.side_effect = [
                Exception("Primary failed"),  # chatgpt fails
                MagicMock(choices=[MagicMock(message=MagicMock(content="Success"))]),  # openai succeeds
            ]

            client = LLMClient(mock_settings_all_providers)
            response = await client.generate_reply(
                messages=[{"role": "user", "content": "Hello"}],
                system_prompt="You are helpful",
            )

            assert response.success is True
            assert response.content == "Success"

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, mock_settings_all_providers):
        """Should return error response when all providers fail."""
        with patch('tg_agent.agent.llm.litellm') as mock_litellm:
            # All providers fail
            mock_litellm.acompletion.side_effect = Exception("Always fails")

            client = LLMClient(mock_settings_all_providers)
            response = await client.generate_reply(
                messages=[{"role": "user", "content": "Hello"}],
                system_prompt="You are helpful",
            )

            assert response.success is False
            assert "All LLM providers failed" in response.error_message

    @pytest.mark.asyncio
    async def test_authentication_error_handling(self, mock_settings_all_providers):
        """Should handle authentication errors gracefully."""
        with patch('tg_agent.agent.llm.litellm') as mock_litellm:
            mock_litellm.AuthenticationError = Exception
            mock_litellm.acompletion.side_effect = Exception("Auth error")

            client = LLMClient(mock_settings_all_providers)
            response = await client.generate_reply(
                messages=[{"role": "user", "content": "Hello"}],
                system_prompt="You are helpful",
            )

            assert response.success is False

    @pytest.mark.asyncio
    async def test_empty_response_handling(self, mock_settings_all_providers):
        """Should handle empty LLM response."""
        with patch('tg_agent.agent.llm.litellm') as mock_litellm:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content=None))]
            mock_litellm.acompletion.return_value = mock_response

            client = LLMClient(mock_settings_all_providers)
            response = await client.generate_reply(
                messages=[{"role": "user", "content": "Hello"}],
                system_prompt="You are helpful",
            )

            assert response.success is False
            assert "Empty response" in response.error_message

    @pytest.mark.asyncio
    async def test_long_response_truncation(self, mock_settings_all_providers):
        """Should truncate responses longer than max_reply_chars."""
        with patch('tg_agent.agent.llm.litellm') as mock_litellm:
            long_text = "x" * 1000  # Longer than max_reply_chars (800)
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content=long_text))]
            mock_litellm.acompletion.return_value = mock_response

            client = LLMClient(mock_settings_all_providers)
            response = await client.generate_reply(
                messages=[{"role": "user", "content": "Hello"}],
                system_prompt="You are helpful",
            )

            assert response.success is True
            assert len(response.content) <= 800
