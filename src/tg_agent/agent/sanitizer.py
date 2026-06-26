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
    r'[,.]?\s*('
    r'привет[!]?\s*|'
    r'ч[её] как сам\??|'
    r'сам как\??|'
    r'а ты как\??|'
    r'а у тебя как\??|'
    r'ты как\??'
    r')\s*$',
    re.IGNORECASE,
)


def clean_reply(text: str, dialog_started: bool, last_user_text: str) -> str:
    text = text.strip()

    if dialog_started:
        text = _GREETING_RE.sub('', text).strip()
        text = re.sub(r'^[!,.\s]+', '', text).strip()

    if any(p in last_user_text.lower() for p in _USER_ASKS_ABOUT_ME):
        text = _FOLLOW_UP_RE.sub('', text).strip()
        text = re.sub(r'\s+', ' ', text).strip()

    return text
