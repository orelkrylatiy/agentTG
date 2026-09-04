# agentTG MCP + Skills

agentTG exposes the already-authorized Telethon session as a local Model Context Protocol (MCP) server so Claude Code or another MCP client can use Telegram as a controlled tool surface.

## Runtime model

There is one long-running agentTG process:

```text
Claude Code ── MCP/HTTP ──┐
Control bot ───────────────┼──> agentTG services ──> Telethon ──> Telegram
Telegram events ───────────┤            │
Skills/workflows ──────────┘            └──> SQLite audit/state
```

The MCP server intentionally runs inside the same process as Telethon. Do not start a second userbot process just for MCP: two processes sharing one Telethon session file are unnecessary and can create locking/session problems.

Default endpoint:

```text
http://127.0.0.1:8765/mcp
```

It is loopback-only by design. For a remote machine, use a private tunnel/VPN rather than binding MCP to a public interface.

## Start

Install dependencies and run agentTG normally:

```bash
pip install -e ".[dev]"
python -m tg_agent.main
```

Relevant `.env` settings:

```env
MCP_ENABLED=true
MCP_HOST=127.0.0.1
MCP_PORT=8765
MCP_ALLOW_WRITES=true
```

`MCP_ALLOW_WRITES=false` is a kill switch for direct MCP sends, mark-read and mutating skills. Telegram monitoring and read/research tools continue to work.

## Claude Code

The repository includes `.mcp.json`, so opening Claude Code from the repository root is the preferred setup. Approve the project MCP server when Claude asks.

Equivalent manual registration:

```bash
claude mcp add --transport http agenttg http://127.0.0.1:8765/mcp
```

Verify the connection with Claude Code's MCP status/list command.

## MCP tools

### Read/research

| Tool | Purpose |
| --- | --- |
| `tg_status` | Connection/account/agent status |
| `tg_list_dialogs` | Recent chats, optionally unread only |
| `tg_unread_chats` | Unread chats plus recent context |
| `tg_get_messages` | Recent messages from a chat/person/channel |
| `tg_search_messages` | Global or chat-scoped Telegram search |
| `tg_chat_info` | Resolve username/link/ID to peer metadata |
| `tg_generate_reply` | Generate a contextual reply without sending |
| `tg_scan_channel` | Read/filter recent channel posts |
| `tg_list_configured_channels` | Monitored channels and outreach policy |
| `tg_list_skills` | Discover reusable workflows |

### Actions

| Tool | Purpose |
| --- | --- |
| `tg_send_message` | Send one explicit message and write an audit record |
| `tg_mark_read` | Mark a chat as read |
| `tg_run_skill` | Run a named workflow; sending workflows default to dry-run |
| `tg_pause_automation` | Pause automatic event processing/outreach |
| `tg_resume_automation` | Resume automatic event processing/outreach |

Direct MCP reads remain available while automatic processing is paused. This lets Claude research Telegram without silently re-enabling auto-replies.

## Internal named skills

Call them through `tg_run_skill(name=..., params=...)`.

| Skill | Default behavior |
| --- | --- |
| `unread_inbox` | Return unread chats with context |
| `contact_context` | Resolve one person/chat and return history |
| `telegram_search` | Search messages |
| `channel_research` | Read a channel and extract Telegram contacts |
| `reply_to_chat` | Generate a reply; `send=false` by default |
| `channel_outreach` | Scan/extract contacts; `send=false` by default |
| `vacancy_hunt` | Research all configured vacancy channels; `send=false` by default |
| `recent_activity` | Read recent audited agent actions |

`channel_outreach` and `vacancy_hunt` reuse the existing SQLite outreach deduplication/rate-limit path. Do not implement bulk outreach as a loop of raw `tg_send_message` calls.

## Claude project skills

The repository also contains Claude Code skills under `.claude/skills/`:

- `/tg-inbox` — triage unread conversations.
- `/tg-research` — read-only Telegram research.
- `/tg-reply` — inspect one conversation and draft/send a reply.
- `/tg-outreach` — controlled channel outreach; manual invocation only.
- `/tg-vacancy-hunt` — research configured vacancy channels and optionally outreach; manual invocation only.

The read-oriented skills may be selected naturally by Claude. Bulk/send-oriented skills declare `disable-model-invocation: true`, so Claude should not decide to launch them as a background side effect without the user invoking the workflow.

## Natural-language examples

Once agentTG and MCP are running, these are intended to work as normal Claude requests:

```text
Посмотри непрочитанные чаты в Telegram и скажи, кому надо ответить.
```

```text
Посмотри переписку с @username и скажи, что там нового.
```

```text
Найди в Telegram всё, где обсуждали React Server Components за последнюю переписку.
```

```text
Посмотри последние 30 сообщений в @some_jobs_channel и выдели интересные вакансии.
```

```text
Напиши @username: "Да, завтра после шести удобно".
```

```text
Сначала посмотри канал @jobs и покажи, кому бы ты написал. Ничего пока не отправляй.
```

```text
Запусти outreach по @jobs максимум на 3 новых контакта.
```

## Sending semantics

There are deliberately two levels:

1. **Primitive action** — `tg_send_message` when the user explicitly asks to send one known message to one target.
2. **Workflow action** — `channel_outreach`, `vacancy_hunt`, etc. for repeated/multi-contact operations. These reuse deduplication, limits and stored state.

Research requests should stay read-only. A phrase such as “посмотри”, “проверь”, “найди” does not imply permission to send. A phrase such as “напиши”, “ответь”, “отправь” is an explicit send instruction for the specified target/scope.

## Testing

CI runs on Python 3.11 and 3.12 and includes:

```bash
python -m compileall -q src tests
ruff check src tests
pytest -q --cov=tg_agent --cov-report=term-missing
```

The MCP tests use the official in-memory MCP client, so tool discovery and invocation go through the MCP protocol layer without opening a TCP port.
