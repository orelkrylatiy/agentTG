# AGENTS.md — Руководство для AI-агентов

> **Назначение:** Этот файл помогает AI-агентам (Nessy, Cursor, Copilot) понимать архитектуру проекта, соглашения и правильные подходы к разработке.

---

## 📋 Обзор проекта

**Telegram AI Userbot Agent** — персональный AI-ассистент для Telegram с:
- **Userbot** (Telethon) — читает/отправляет сообщения от вашего имени
- **Control Bot** (aiogram) — управление через команды и HITL-утверждение
- **LLM** (LiteLLM) — генерация ответов через ChatGPT/OpenAI/OpenRouter
- **Policy Engine** — режимы чатов, фильтры, cooldown'ы

### Ключевые возможности

| Функция | Описание |
|---------|----------|
| **Outreach** | Автоматический поиск контактов в каналах и отправка сообщений |
| **Reply** | Генерация ответов на входящие сообщения |
| **HITL** | Draft-режим: ответы на утверждение перед отправкой |
| **Channel Monitoring** | Мониторинг каналов с фильтрацией по ключевым словам |
| **Custom Prompts** | Кастомные промпты на канал/чат через файловую систему |

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         Telegram API                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        │                                 │
        ▼                                 ▼
┌───────────────────┐           ┌───────────────────┐
│   Userbot         │           │   Control Bot     │
│   (Telethon)      │           │   (aiogram)       │
│   - client.py     │           │   - bot.py        │
│   - handlers.py   │           │   - handlers.py   │
│   - sender.py     │           │   - hitl.py       │
└─────────┬─────────┘           └─────────┬─────────┘
          │                               │
          │         ┌─────────────────────┤
          │         │                     │
          ▼         ▼                     ▼
    ┌─────────────────────────────────────────┐
    │           Policy & Storage              │
    │  - policy/gate.py (режимы, фильтры)    │
    │  - policy/modes.py (OFF/WATCH/DRAFT/AUTO)│
    │  - policy/cooldown.py (rate limiting)  │
    │  - storage/db.py (SQLite + SQLModel)   │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │           LLM & Prompts                 │
    │  - agent/llm.py (LiteLLM клиент)        │
    │  - agent/prompts.py (загрузка промптов) │
    │  - agent/reply.py (генерация ответов)   │
    │  - agent/sanitizer.py (очистка вывода)  │
    └─────────────────────────────────────────┘
```

---

## 📁 Структура кодовой базы

```
src/tg_agent/
├── main.py                 # Точка входа, оркестрация компонентов
├── config.py               # Настройки (pydantic-settings, .env)
├── logging.py              # Настройка логирования (loguru)
├── smoke_llm.py            # Smoke-тест LLM-подключения
│
├── agent/                  # LLM и промпты
│   ├── llm.py              # LiteLLM клиент, fallback-цепочка
│   ├── prompts.py          # Загрузка промптов из файлов
│   ├── reply.py            # Генерация ответов
│   ├── sanitizer.py        # Очистка вывода LLM
│   └── models.py           # Data-модели для ответов
│
├── userbot/                # Telethon userbot
│   ├── client.py           # Клиент, подключение, сессия
│   ├── handlers.py         # Обработка входящих сообщений
│   ├── channel_handler.py  # Мониторинг каналов, outreach
│   ├── channel_config.py   # Конфигурация каналов
│   └── sender.py           # Отправка сообщений (с задержками)
│
├── control_bot/            # aiogram control bot
│   ├── bot.py              # Бот, dispatcher
│   ├── handlers.py         # Команды (/start, /status, /mode...)
│   ├── hitl.py             # HITL: approve/reject drafts
│   └── keyboards.py        # Inline-кнопки для HITL
│
├── policy/                 # Policy engine
│   ├── modes.py            # ChatMode: OFF/WATCH/DRAFT/AUTO
│   ├── gate.py             # PolicyGate: решения на основе режима
│   ├── filters.py          # MessageFilter: боты, деньги, коммиты
│   └── cooldown.py         # CooldownManager: rate limiting
│
├── storage/                # БД и репозитории
│   ├── db.py               # Database: сессии, init
│   ├── models.py           # SQLModel: ChatSettings, MessageLog...
│   └── repositories.py     # Репозитории для CRUD
│
└── humanizer/              # Эмуляция человека
    └── delays.py           # TypingDelaySimulator: задержки печати
```

---

## ⚙️ Конфигурация

### Переменные окружения (.env)

```env
# Telegram (обязательно)
TG_API_ID=123456
TG_API_HASH=your_hash
TG_PHONE=+79990000000
CONTROL_BOT_TOKEN=bot:token
OWNER_TELEGRAM_ID=123456789

# LLM (выбери один)
LLM_PROVIDER=openai              # или chatgpt_oauth, openrouter
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# Агент (безопасно по умолчанию)
AGENT_GLOBAL_ENABLED=false       # false = агент паузой
DEFAULT_CHAT_MODE=DRAFT          # DRAFT = все ответы на утверждение

# Outreach
MONITORED_CHANNELS=-1001782596777:Title:outreach
```

### Промпты (файловая система)

```
prompts/
├── outreach/
│   ├── default.txt           # Для всех каналов
│   └── {channel_id}.txt      # Кастомный для канала
├── reply/
│   ├── default.txt           # Для всех чатов
│   └── {chat_id}.txt         # Кастомный для чата
└── PROMPTS_SPEC.md           # Спецификация
```

**Логика выбора:**
- **Outreach:** `{channel_id}.txt` → `default.txt`
- **Reply:** `{chat_id}.txt` → `default.txt`

---

## 🎯 Режимы чатов (Chat Modes)

| Режим | Поведение | Когда использовать |
|-------|-----------|-------------------|
| `OFF` | Игнорирует чат | Спам, ненужные контакты |
| `WATCH` | Только уведомления | Важные чаты, но без автоответов |
| `DRAFT` | Генерирует ответ на утверждение | По умолчанию, безопасный режим |
| `AUTO` | Автоответ без утверждения | Только для trusted-контактов |

**Безопасность:**
- `AUTO` работает только для `is_trusted=True`
- `AGENT_GLOBAL_ENABLED=false` по умолчанию
- Фильтры: боты, деньги, обязательства → всегда DRAFT

---

## 🔧 Команды разработки

### Запуск

```bash
# Быстрый старт
./start.sh

# Вручную (dev)
source .venv/bin/activate
python -m tg_agent.main

# Smoke-тест LLM
python -m tg_agent.smoke_llm
```

### Тесты

```bash
# Все тесты
pytest

# С покрытием
pytest --cov=tg_agent --cov-report=html

# Конкретный тест
pytest tests/test_policy.py -v
```

### Линтеры

```bash
# Ruff (lint + format)
ruff check src/tg_agent
ruff format src/tg_agent

# Black
black src/tg_agent

# MyPy (type check)
mypy src/tg_agent
```

---

## 📝 Соглашения по коду

### Стилистика

- **Типизация:** Аннотации типов обязательны (`def foo(x: int) -> str:`)
- **Имена:** `snake_case` для функций/переменных, `PascalCase` для классов
- **Длина строки:** 100 символов (настроено в `pyproject.toml`)
- **Docstrings:** Google-style для публичных API

### Паттерны

#### 1. Репозитории (storage/repositories.py)

```python
class ChatSettingsRepo:
    def __init__(self, session: Session):
        self.session = session

    def get_by_chat_id(self, chat_id: int) -> ChatSettings | None:
        return self.session.get(ChatSettings, chat_id)

    def create(self, ...) -> ChatSettings:
        chat = ChatSettings(...)
        self.session.add(chat)
        self.session.commit()
        return chat
```

#### 2. Policy Gate (policy/gate.py)

```python
class PolicyGate:
    def decide(self, chat: ChatSettings, message: Message) -> PolicyDecision:
        if chat.mode == ChatMode.OFF:
            return PolicyDecision.IGNORE
        elif chat.mode == ChatMode.DRAFT:
            return PolicyDecision.DRAFT
        # ...
```

#### 3. LLM Client (agent/llm.py)

```python
class LLMClient:
    async def generate_reply(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> LLMResponse:
        # Пробует провайдеры по цепочке
        # Fallback: primary → openai → openrouter
```

### Обработка ошибок

```python
# Логирование через loguru
logger.info(f"Generated reply for chat {chat_id}")
logger.warning(f"LLM failed: {error_message}")
logger.error(f"Database error: {exc}", exc_info=True)

# Graceful degradation
if not llm_response.success:
    return GeneratedReply(
        text="",
        success=False,
        error_message=llm_response.error_message,
    )
```

---

## 🚀 Типичные задачи

### Добавить новую команду бота

1. **handlers.py:** Добавить handler
```python
@router.message(Command("mycommand"))
async def my_command_handler(message: types.Message, ...):
    await message.answer("Response")
```

2. **bot.py:** Зарегистрировать команду
```python
BotCommand(command="mycommand", description="Описание")
```

### Добавить новое поле в БД

1. **models.py:** Обновить модель
```python
class ChatSettings(SQLModel, table=True):
    chat_id: int = Field(primary_key=True)
    new_field: str = Field(default="")  # ← новое поле
```

2. **repositories.py:** Обновить репозиторий
```python
def update_new_field(self, chat_id: int, value: str) -> None:
    chat = self.get_by_chat_id(chat_id)
    if chat:
        chat.new_field = value
        self.session.commit()
```

3. **Миграция:** Вручную или через Alembic (если подключен)

### Добавить новый промпт

1. **Создать файл:**
```bash
nano prompts/outreach/-1001111111.txt
```

2. **Написать текст:**
```
Ты — опытный разработчик, предлагаешь менторство...
```

3. **Перезапустить агента:**
```bash
./start.sh
```

---

## 🧪 Тестирование

### Unit-тесты (tests/)

```python
# tests/test_policy.py
def test_policy_gate_off_mode():
    chat = ChatSettings(chat_id=1, mode=ChatMode.OFF)
    gate = PolicyGate(...)
    decision = gate.decide(chat, message)
    assert decision == PolicyDecision.IGNORE
```

### Интеграционные тесты

```bash
# Smoke-тест LLM
python -m tg_agent.smoke_llm

# Проверка БД
sqlite3 data/agent.db "SELECT * FROM chat_settings;"
```

### Ручное тестирование

1. Запустить агента
2. Написать в control bot: `/status`
3. Отправить тестовое сообщение в чат
4. Проверить draft в control bot

---

## 🐛 Отладка

### Логи

```bash
# Последние 50 строк
tail -50 /tmp/agent.log

# В реальном времени
tail -f /tmp/agent.log

# Поиск ошибок
grep ERROR /tmp/agent.log
```

### Отладка LLM

```python
# В agent/llm.py добавить логирование
logger.debug(f"LLM request: {messages}")
logger.debug(f"LLM response: {response}")
```

### Отладка БД

```bash
# SQLite CLI
sqlite3 data/agent.db

# Посмотреть чаты
SELECT chat_id, mode, is_trusted FROM chat_settings;

# Посмотреть pending actions
SELECT * FROM pending_actions WHERE status='pending';
```

---

## ⚠️ Безопасность

### Никогда не коммить

- `.env` — с секретами
- `data/userbot.session` — сессия Telethon
- `data/litellm/chatgpt/auth.json` — токены OAuth

### Безопасные значения по умолчанию

```env
AGENT_GLOBAL_ENABLED=false    # Агент выключен
DEFAULT_CHAT_MODE=DRAFT       # Все ответы на утверждение
REQUIRE_APPROVAL_FOR_UNKNOWN_CHATS=true
```

### Валидация

- `CHATGPT_API_BASE` → только `https` + разрешённые хосты
- `CHATGPT_TOKEN_DIR` → только внутри проекта
- `OPENAI_API_KEY` → не пустая строка

---

## 📚 Дополнительные ресурсы

- **README.md** — полная документация пользователя
- **prompts/PROMPTS_SPEC.md** — спецификация системы промптов
- **pyproject.toml** — зависимости, настройки линтеров
- **.env.example** — шаблон конфига

---

## 🔄 Changelog

### 2026-07-09
- ✅ Добавлена система кастомных промптов (файлы)
- ✅ `prompts/outreach/{channel_id}.txt` — для каналов
- ✅ `prompts/reply/{chat_id}.txt` — для чатов
- ✅ Fallback на `default.txt` если файл не найден
- ✅ Создан `AGENTS.md` для AI-агентов

---

**Версия:** 1.0
**Дата:** 2026-07-09
**Статус:** Active
