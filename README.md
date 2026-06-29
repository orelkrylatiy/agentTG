# Telegram AI Userbot Agent

Personal Telegram AI userbot agent with control bot and Human-in-the-Loop (HITL) approval.

## ⚠️ Important Warnings

**Before using this project:**

1. **Use a test Telegram account** — Do NOT use your primary Telegram account. Register a separate account on a spare phone number (e.g. a secondary SIM or a virtual number) and test against that.
2. **Telegram ToS** — Userbot automation may violate Telegram Terms of Service. Use at your own risk.
3. **Start in safe mode** — Agent starts with `AGENT_GLOBAL_ENABLED=false` and `DEFAULT_CHAT_MODE=DRAFT`. Never enable AUTO mode for untrusted chats.
4. **Privacy** — All messages are processed locally. LLM providers receive message content for reply generation.

## What This Is

A personal AI assistant that:
- Connects to your Telegram account via userbot (Telethon)
- Reads incoming messages in configured chats
- Generates replies using LLM (ChatGPT via LiteLLM OAuth, or fallback providers)
- Sends drafts to a control bot for approval (HITL)
- Can auto-reply in trusted chats (with safety checks)

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Telegram API   │────▶│  Telethon        │────▶│  Incoming       │
│  (User Account) │     │  Userbot         │     │  Message Handler│
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
┌─────────────────┐     ┌──────────────────┐     ┌────────▼────────┐
│  Control Bot    │◀────│  Policy Gate     │◀────│  Chat Settings  │
│  (aiogram)      │     │  (Modes/Filters) │     │  (SQLite)       │
└────────┬────────┘     └──────────────────┘     └─────────────────┘
         │                       │
         │  Approve/Reject       │
         │                       ▼
         │              ┌──────────────────┐
         │              │  LLM Client      │
         │              │  (LiteLLM)       │
         │              └────────┬─────────┘
         │                       │
         ▼                       ▼
┌─────────────────────────────────────────────────┐
│              Reply Generation                   │
│  (System Prompt + Context + Incoming Message)   │
└─────────────────────────────────────────────────┘
```

### Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| Userbot | Telethon | Connect to Telegram account, read/send messages |
| Control Bot | aiogram 3.x | Owner commands, draft approval, status |
| Database | SQLite + SQLModel | Chat settings, message logs, pending actions |
| LLM Client | LiteLLM | Unified interface for multiple LLM providers |
| Policy Engine | Custom | Mode decisions, safety filters, cooldowns |

### Why Not MCP in MVP?

MCP (Model Context Protocol) is useful for connecting external tools to AI agents. However, for this MVP:

- **Simplicity** — Direct Telethon connection is simpler than MCP server setup
- **Fewer moving parts** — No need for separate MCP server process
- **Faster iteration** — Easier to test and debug locally
- **Lower latency** — Direct API calls vs. MCP protocol overhead

MCP can be added later (Phase 2) when you want to expose Telegram as a tool to external agents.

## Installation

### Prerequisites

- Python 3.11 or 3.12
- Telegram API credentials (from my.telegram.org)
- Telegram bot token (from @BotFather)

### Step 1: Get Telegram Credentials

1. Go to [my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Click "API development tools"
4. Create a new application
5. Copy `api_id` and `api_hash`

### Step 2: Create Control Bot

1. Open Telegram and find @BotFather
2. Send `/newbot`
3. Follow prompts to create bot
4. Copy the bot token

### Step 3: Find Your Telegram ID

Use @userinfobot or @getmyid_bot to find your numeric Telegram ID.

### Step 4: Clone and Setup

```bash
# Clone repository
git clone <repository-url>
cd telegram-ai-userbot-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env
```

### Step 5: Configure .env

Edit `.env` with your credentials:

```env
# Required
TG_API_ID=123456
TG_API_HASH=your_api_hash_here
TG_PHONE=+1234567890
CONTROL_BOT_TOKEN=bot:token_here
OWNER_TELEGRAM_ID=123456789

# Recommended
AGENT_GLOBAL_ENABLED=false
DEFAULT_CHAT_MODE=DRAFT
```

### Step 6: First Run

```bash
python -m tg_agent.main
```

On first run, Telethon will prompt for the login code sent to your Telegram. Enter it in the terminal.

### Step 6.5: Verify Subscription OAuth Before Telegram Testing

If you want the agent to use your ChatGPT subscription through LiteLLM, validate that path first:

```bash
python -m tg_agent.smoke_llm
```

Do this before debugging Telegram message handling. The correct order is:
1. make `chatgpt_oauth` work
2. confirm tokens are persisted under `data/litellm/chatgpt/`
3. only then start `python -m tg_agent.main`

## LLM Configuration

### ChatGPT OAuth (Primary)

This project uses LiteLLM's ChatGPT OAuth provider to leverage your ChatGPT Plus subscription.

**Recommended setup flow:**

1. Configure `.env`:
   ```env
   LLM_PROVIDER=chatgpt_oauth
   LLM_MODEL=chatgpt/gpt-5
   LITELLM_CHATGPT_ENABLED=true
   CHATGPT_TOKEN_DIR=data/litellm/chatgpt
   CHATGPT_AUTH_FILE=auth.json
   CHATGPT_API_BASE=https://chatgpt.com/backend-api/codex
   CHATGPT_ORIGINATOR=codex_cli_rs
   ```

2. Run the smoke test:
   ```bash
   python -m tg_agent.smoke_llm
   ```

3. If LiteLLM starts device-code auth, complete that login in the browser with the subscription account you want the Telegram agent to use.

4. Confirm token files appear in `data/litellm/chatgpt/`. These files must survive restarts and Docker container recreation.

5. Only after the smoke test succeeds, run the full Telegram agent:
   ```bash
   python -m tg_agent.main
   ```

**Optional:**

Install LiteLLM proxy extras if you need them:
   ```bash
   pip install 'litellm[proxy]'
   ```

If ChatGPT OAuth fails on your machine or VPS, switch providers through `.env` and use the fallback path.

**Security constraints on OAuth settings:**

For safety, the config layer validates the ChatGPT OAuth variables and will refuse to start otherwise:

- `CHATGPT_API_BASE` must use `https` and point at an allowed host (`chatgpt.com` or `chat.openai.com`) with a path under `/backend-api/`.
- `CHATGPT_TOKEN_DIR` must resolve inside the project root (no `..` traversal, no absolute path outside the repo).
- `CHATGPT_AUTH_FILE` must be a single relative file name (no nested or absolute paths).

The token directory is created automatically on startup; in Docker it is also persisted via the `./data/litellm` volume.

### OpenAI Fallback

If you have an OpenAI API key:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_FALLBACK_MODEL=gpt-4o-mini
```

### OpenRouter Fallback

OpenRouter provides access to multiple models:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_FALLBACK_MODEL=openrouter/openai/gpt-4o-mini
```

### Provider Fallback Chain

The agent tries providers in this order:
1. Primary provider (from `LLM_PROVIDER`)
2. OpenAI (if key configured)
3. OpenRouter (if key configured)

If all providers fail, the agent creates a draft with an error message for owner review.

## Control Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Start interaction with bot |
| `/status` | Show agent status and statistics |
| `/pause` | Pause agent (stop processing messages) |
| `/resume` | Resume agent |
| `/chats` | List all configured chats |
| `/mode <chat> <mode>` | Set chat mode (OFF/WATCH/DRAFT/AUTO) |
| `/trust <chat>` | Mark chat as trusted (allows AUTO) |
| `/untrust <chat>` | Remove trusted status |
| `/send <chat> <msg>` | Send message (requires approval) |
| `/recent` | Show recent agent actions |
| `/style` | Show prompt configuration |
| `/help` | Show help message |
| `/scan_channel [N]` | Scan last N posts from monitored channels (default: 10) |

## Channel Monitoring

The agent can monitor Telegram channels for new posts, extract contact information, and automatically send personalized outreach messages.

### Configuration

Add channels to `.env`:

```bash
MONITORED_CHANNELS="-1001782596777:IT Jobs:outreach,-1001234567890:Design:outreach:figma,ui"
```

**Format:** `channel_id[:Title][:outreach][:keyword1,keyword2]`

| Parameter | Required | Description |
|-----------|----------|-------------|
| `channel_id` | ✅ | Telegram channel ID (e.g., `-1001782596777`) |
| `Title` | ❌ | Human-readable name for logging |
| `outreach` | ❌ | Enable automatic DM to contacts |
| `keywords` | ❌ | Filter posts by keywords (comma-separated) |

### Examples

**Monitor only (no auto-outreach):**
```bash
MONITORED_CHANNELS="-1001782596777:IT Jobs"
```

**Auto-outreach to all contacts:**
```bash
MONITORED_CHANNELS="-1001782596777:IT Jobs:outreach"
```

**Auto-outreach with keyword filter:**
```bash
MONITORED_CHANNELS="-1001782596777:IT:outreach:python,frontend"
```

**Multiple channels:**
```bash
MONITORED_CHANNELS="-1001782596777:IT:outreach:python,-1001234567890:Design:outreach:figma"
```

### How It Works

1. **Monitor**: Agent listens for new posts in configured channels
2. **Extract**: Parses `@username` and `t.me/username` from post text
3. **Generate**: Creates personalized message using LLM
4. **Send**: Sends DM via your userbot account
5. **Track**: Saves contacted usernames to `data/contacted.json` (no duplicates)

### Manual Outreach

Run one-time outreach scan:

```bash
# Scan last 10 posts from all configured channels
python outreach.py 10

# Scan specific channel
python outreach.py 10 -1001782596777
```

### Rate Limiting

Each channel has built-in rate limiting:
- Default: 60 posts per hour maximum
- Prevents spam and API limits
- Configurable per channel via `max_posts_per_hour`

### Finding Channel ID

Use one of these methods:

1. **Forward to @getmyidbot** — Forward a post from the channel, bot shows ID
2. **Use the script** — Run `python get_channel_id.py`
3. **Manual** — ID format is `-100` + 10 digits (e.g., `-1001782596777`)

## Chat Modes

| Mode | Behavior |
|------|----------|
| `OFF` | Agent ignores this chat completely |
| `WATCH` | Agent notifies owner about messages, doesn't reply |
| `DRAFT` | Agent generates reply draft for owner approval |
| `AUTO` | Agent replies automatically (trusted chats only) |

### Mode Recommendations

- **Unknown chats**: Start with `OFF` or `WATCH`
- **Important contacts**: Use `DRAFT` for review
- **Trusted frequent chats**: Consider `AUTO` after testing
- **Never use AUTO** for: groups, unknown contacts, business chats

## Safety Features

### Built-in Protections

1. **Global pause** — Agent starts disabled (`AGENT_GLOBAL_ENABLED=false`)
2. **Draft by default** — `DEFAULT_CHAT_MODE=DRAFT` requires approval
3. **Trusted requirement** — AUTO mode only works for trusted chats
4. **Cooldown** — Prevents spam (default 120 seconds between replies)
5. **Owner takeover** — Pauses after owner activity
6. **Bot filtering** — Doesn't reply to bot messages
7. **Money/commitment detection** — Flags sensitive topics for review

### Sensitive Topic Detection

The agent automatically requires manual review for messages involving:
- Money, payments, transfers
- Meetings, appointments, deadlines
- Commitments, promises, guarantees
- Conflict, complaints, aggression
- Personal data (phone, address, cards)

## Human-in-the-Loop (HITL)

When a draft is generated:

1. Control bot sends message with proposed reply
2. Message includes `[✅ Approve]` and `[❌ Reject]` buttons
3. Owner clicks to approve or reject
4. Approved messages are sent via userbot
5. All actions are logged in SQLite

## Database Schema

### ChatSettings
- `id`, `chat_id`, `chat_title`
- `mode` (OFF/WATCH/DRAFT/AUTO)
- `is_trusted`
- `last_incoming_message_id`
- `last_agent_reply_at`
- `paused_until`

### MessageLog
- `id`, `chat_id`, `message_id`
- `sender_id`, `direction`
- `text`, `created_at`

### PendingAction
- `id`, `action_type` (reply/send_message)
- `chat_id`, `reply_to_message_id`
- `text`, `status`
- `created_at`, `decided_at`

### GlobalState
- Key-value store for agent settings

## Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

**Note:** Session file and database are persisted in `./data/`

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=tg_agent --cov-report=html

# Run specific test
pytest tests/test_policy.py -v
```

> Note: the project targets Python 3.11/3.12. On systems where `python` points at Python 2, use `python3 -m pytest`.

To check live LLM/OAuth connectivity (not a unit test, makes a real provider call):

```bash
python -m tg_agent.smoke_llm
```

## Project Structure

```
telegram-ai-userbot-agent/
├── README.md
├── .env.example
├── .gitignore
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
├── prompts/
│   ├── system.ru.txt      # Main system prompt
│   └── safety.ru.txt      # Safety constraints
├── src/tg_agent/
│   ├── __init__.py
│   ├── main.py            # Entry point
│   ├── config.py          # Settings
│   ├── logging.py         # Logging setup
│   ├── smoke_llm.py       # LLM/OAuth connectivity smoke test
│   ├── userbot/
│   │   ├── client.py      # Telethon client
│   │   ├── handlers.py    # Message handlers
│   │   └── sender.py      # Message sender
│   ├── control_bot/
│   │   ├── bot.py         # aiogram bot
│   │   ├── handlers.py    # Command handlers
│   │   ├── keyboards.py   # Inline keyboards
│   │   └── hitl.py        # HITL approval
│   ├── agent/
│   │   ├── llm.py         # LLM client
│   │   ├── prompts.py     # Prompt management
│   │   ├── reply.py       # Reply generation
│   │   └── models.py      # Agent models
│   ├── policy/
│   │   ├── modes.py       # Chat modes
│   │   ├── filters.py     # Message filters
│   │   ├── cooldown.py    # Rate limiting
│   │   └── gate.py        # Policy decisions
│   ├── storage/
│   │   ├── db.py          # Database
│   │   ├── models.py      # SQLModel tables
│   │   └── repositories.py# Data access
│   └── humanizer/
│       └── delays.py      # Typing simulation
└── tests/
    ├── test_policy.py
    ├── test_cooldown.py
    ├── test_hitl.py
    ├── test_llm_provider_selection.py
    ├── test_oauth_config.py        # ChatGPT OAuth config hardening
    └── test_smoke_llm.py           # smoke_llm entrypoint
```

## Roadmap

### Phase 2 (Future)

- [ ] MCP layer via fast-mcp-telegram
- [ ] Pydantic AI integration
- [ ] Task scheduler for delayed actions
- [ ] Channel summaries and digests
- [ ] RAG with Qdrant for long-term memory
- [ ] Voice messages via Whisper
- [ ] Multi-agent workflows
- [ ] Web dashboard

### Phase 3 (Advanced)

- [ ] Fine-tuned models for specific style
- [ ] Multi-account support
- [ ] Advanced analytics
- [ ] Integration with external tools (calendar, tasks)

## Troubleshooting

### "TG_API_HASH must be set"
- Copy `.env.example` to `.env`
- Fill in your actual API credentials

### "CONTROL_BOT_TOKEN must be set"
- Create a bot via @BotFather
- Add the token to `.env`

### Login code not received
- Wait a few minutes
- Try restarting the application
- Check if phone number is correct in `.env`

### LLM provider fails
- Check if API keys are valid
- Try switching to a different provider
- Check network connectivity

### Messages not being processed
- Check `/status` — agent may be paused
- Verify chat mode is not `OFF`
- Check logs for errors

## License

MIT License — see LICENSE file.

## Disclaimer

This project is for educational and personal use only. The authors are not responsible for:
- Violation of Telegram Terms of Service
- Account bans or restrictions
- Misuse of the software
- Any damages resulting from use

Use responsibly and at your own risk.
