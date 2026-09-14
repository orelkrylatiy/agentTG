from tg_agent.agent.sanitizer import clean_reply, normalize_telegram_style


def test_normalize_telegram_style_replaces_typographic_dashes():
    text = "Senior Engineer — интересная роль, fullstack–разработка"

    assert normalize_telegram_style(text) == (
        "Senior Engineer - интересная роль, fullstack-разработка"
    )


def test_clean_reply_applies_style_normalization_after_cleanup():
    text = "Привет! Да — завтра после шести удобно"

    assert clean_reply(
        text,
        dialog_started=True,
        last_user_text="Когда удобно?",
        context_turns=[],
    ) == "Да - завтра после шести удобно"
