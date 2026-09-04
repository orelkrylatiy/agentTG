from tg_agent.config import Settings


def test_channel_config_keeps_keyword_commas_and_splits_later_channels():
    settings = Settings(
        TG_API_ID=123456,
        TG_API_HASH="test_hash",
        TG_PHONE="+1234567890",
        CONTROL_BOT_TOKEN="bot:test",
        OWNER_TELEGRAM_ID=123456,
        MONITORED_CHANNELS=(
            "-1001:IT:outreach:python,frontend,-1002:Design:outreach:figma,ui"
        ),
    )

    configs = settings.channel_configs

    assert [config.channel_id for config in configs] == [-1001, -1002]
    assert configs[0].keywords == ["python", "frontend"]
    assert configs[1].keywords == ["figma", "ui"]
    assert settings.monitored_channel_ids == [-1001, -1002]
