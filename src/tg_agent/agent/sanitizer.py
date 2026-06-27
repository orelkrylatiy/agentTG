import re

_GREETING_RE = re.compile(
    r'^(привет|здарова|хай|hi|hello)[!?,.\s]*',
    re.IGNORECASE,
)

_USER_ASKS_ABOUT_ME = (
    'а у тебя', 'ты как', 'как сам', 'а ты как',
    'сам как', 'как ты', 'а ты?',
)

_FOLLOW_UP_RE = re.compile(
    r'[,!.]?\s*('
    r'привет[!]?\s*|'
    r'ч[её] как сам\??|'
    r'сам как\??|'
    r'а ты как\??|'
    r'а у тебя как\??|'
    r'ты как\??|'
    r'как дела\??|'
    r'как у тебя дела\??|'
    r'как сам\??'
    r')\s*$',
    re.IGNORECASE,
)

# Whether the last assistant message already contained a follow-up question
_ASSISTANT_ALREADY_ASKED_RE = re.compile(
    r'(а у тебя|ты как|как сам|а ты|сам как|как ты|как дела|как у тебя)\??[\s]*$',
    re.IGNORECASE,
)


def _agent_already_asked(context_turns: list[dict]) -> bool:
    """Return True if the most recent assistant turn already ended with a question."""
    for turn in reversed(context_turns):
        if turn["role"] == "assistant":
            return bool(_ASSISTANT_ALREADY_ASKED_RE.search(turn["content"].strip()))
    return False


def clean_reply(
    text: str,
    dialog_started: bool,
    last_user_text: str,
    context_turns: list[dict] | None = None,
) -> str:
    text = text.strip()

    if dialog_started:
        text = _GREETING_RE.sub('', text).strip()
        text = re.sub(r'^[!,.\s]+', '', text).strip()

    # Strip follow-up if: user asked about agent, OR agent already asked in previous turn
    user_asked = any(p in last_user_text.lower() for p in _USER_ASKS_ABOUT_ME)
    agent_asked = _agent_already_asked(context_turns or [])

    if user_asked or agent_asked:
        text = _FOLLOW_UP_RE.sub('', text).strip()
        text = re.sub(r'\s+', ' ', text).strip()

    return text
