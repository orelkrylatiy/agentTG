"""
Tests for ChatGPT OAuth configuration hardening.
"""

from pathlib import Path

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("pydantic_settings")

from tg_agent.config import Settings


def build_settings(**overrides) -> Settings:
    base = {
        "TG_API_ID": 123456,
        "TG_API_HASH": "test_hash",
        "TG_PHONE": "+1234567890",
        "CONTROL_BOT_TOKEN": "bot:test_token",
        "OWNER_TELEGRAM_ID": 123456,
    }
    base.update(overrides)
    return Settings(**base)


def test_chatgpt_api_base_allows_default_host():
    settings = build_settings(CHATGPT_API_BASE="https://chatgpt.com/backend-api/codex")
    assert settings.chatgpt_api_base == "https://chatgpt.com/backend-api/codex"


def test_chatgpt_api_base_rejects_untrusted_host():
    with pytest.raises(ValueError):
        build_settings(CHATGPT_API_BASE="https://evil.example.com/backend-api/codex")


def test_chatgpt_token_dir_rejects_parent_traversal():
    with pytest.raises(ValueError):
        build_settings(CHATGPT_TOKEN_DIR="../outside")


def test_chatgpt_auth_file_rejects_nested_paths():
    with pytest.raises(ValueError):
        build_settings(CHATGPT_AUTH_FILE="nested/auth.json")


def test_chatgpt_token_dir_resolves_inside_project():
    settings = build_settings(CHATGPT_TOKEN_DIR="data/litellm/chatgpt")
    assert settings.chatgpt_token_dir_path.is_relative_to(settings.project_root)
    assert settings.chatgpt_auth_file_path == settings.chatgpt_token_dir_path / "auth.json"


def test_chatgpt_token_dir_rejects_absolute_outside_project(tmp_path: Path):
    outside = tmp_path / "oauth"
    outside.mkdir()
    with pytest.raises(ValueError):
        build_settings(CHATGPT_TOKEN_DIR=str(outside)).chatgpt_token_dir_path
