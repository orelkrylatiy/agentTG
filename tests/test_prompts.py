from pathlib import Path

from tg_agent.agent.prompts import PromptManager
from tg_agent.config import Settings
from tg_agent.userbot.channel_handler import ChannelHandler


def _make_manager(tmp_path: Path) -> PromptManager:
    settings = Settings()
    manager = PromptManager(settings)
    manager.prompts_dir = tmp_path
    manager.outreach_prompts_dir = tmp_path / "outreach"
    manager.reply_prompts_dir = tmp_path / "reply"
    manager.outreach_prompts_dir.mkdir(parents=True, exist_ok=True)
    manager.reply_prompts_dir.mkdir(parents=True, exist_ok=True)
    return manager


def test_reply_system_prompt_preserves_global_layers_and_adds_chat_prompt(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    (tmp_path / "system.ru.txt").write_text("system", encoding="utf-8")
    (tmp_path / "persona.ru.txt").write_text("persona", encoding="utf-8")
    (tmp_path / "safety.ru.txt").write_text("safety", encoding="utf-8")
    (tmp_path / "reply" / "123.txt").write_text("custom reply", encoding="utf-8")

    prompt = manager.get_reply_system_prompt(123)

    assert prompt == "system\n\npersona\n\nsafety\n\ncustom reply"


def test_empty_custom_reply_prompt_falls_back_to_default(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    (tmp_path / "reply" / "123.txt").write_text(" \n ", encoding="utf-8")
    (tmp_path / "reply" / "default.txt").write_text("default reply", encoding="utf-8")

    assert manager.get_reply_prompt(123) == "default reply"


def test_empty_default_outreach_prompt_falls_back_to_hardcoded_prompt(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    (tmp_path / "outreach" / "default.txt").write_text("\n", encoding="utf-8")

    prompt = manager.get_outreach_prompt(-100123)

    assert "фронтенд-разработчик с 5 годами опыта" in prompt


def test_channel_handler_creates_prompt_manager_when_omitted() -> None:
    settings = Settings()
    handler = ChannelHandler(
        settings=settings,
        client=object(),
        control_bot=object(),
        db=object(),
        llm_client=None,
        prompt_manager=None,
    )

    assert isinstance(handler.prompt_manager, PromptManager)
