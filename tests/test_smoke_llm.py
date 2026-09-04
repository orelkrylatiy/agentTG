"""
Tests for smoke_llm entrypoint behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("pydantic_settings")

from tg_agent import smoke_llm


@pytest.mark.asyncio
async def test_smoke_llm_returns_zero_on_success(capsys):
    response = MagicMock(provider=MagicMock(value="chatgpt_oauth"), model="chatgpt/gpt-5", success=True, error_message=None, content="CHATGPT_OAUTH_OK")
    client = MagicMock()
    client.smoke_test = AsyncMock(return_value=response)

    with patch("tg_agent.smoke_llm.get_settings", return_value=MagicMock()), patch(
        "tg_agent.smoke_llm.setup_logging"
    ), patch("tg_agent.smoke_llm.LLMClient", return_value=client):
        result = await smoke_llm.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "success=True" in captured.out


@pytest.mark.asyncio
async def test_smoke_llm_returns_one_on_init_error(capsys):
    with patch("tg_agent.smoke_llm.get_settings", return_value=MagicMock()), patch(
        "tg_agent.smoke_llm.setup_logging"
    ), patch("tg_agent.smoke_llm.LLMClient", side_effect=RuntimeError("boom")):
        result = await smoke_llm.main()

    captured = capsys.readouterr()
    assert result == 1
    assert "smoke_test_failed=boom" in captured.err
