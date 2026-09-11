# agentTG architecture: Telegram execution plane + durable automation

This document describes the current architecture and the intended next evolution of agentTG.

Research behind the design decisions is summarized in [`RESEARCH_AGENT_AUTOMATION_PATTERNS.md`](RESEARCH_AGENT_AUTOMATION_PATTERNS.md).

## Goal

agentTG is a **single Telegram execution core** controlled from several surfaces:

- Claude Code / another AI agent through MCP;
- Telegram control bot;
- live Telegram events;
- reusable named workflows/skills;
- future persistent watches and schedules.

All surfaces should reuse the same services, policy and state. They must not each implement their own Telegram side effects.

## Core rule

> LLMs decide wording and semantic interpretation. Deterministic code decides permissions and side effects.

Telegram messages and channel posts are untrusted input. Instructions contained inside Telegram content must never expand the permissions of the MCP client, workflow or agent processing them.

## Current runtime

Today agentTG intentionally uses **one long-running process**:

```text
Claude Code
    |
    | MCP Streamable HTTP
    | http://127.0.0.1:8765/mcp
    v
+-------------------------------------------------+
|                  agentTG daemon                 |
|                                                 |
| MCP Server ----------+                          |
| Control Bot ---------+--> TelegramService       |
| Telegram events -----+        |                 |
| Skills --------------+        |                 |
|                               +--> Policy       |
|                               +--> LLM          |
|                               +--> Outreach     |
|                               +--> Audit/SQLite |
|                               +--> Telethon     |
+--------------------------------------|----------+
                                       v
                                   Telegram
```

Important invariant: **exactly one process owns the Telethon session**.

The MCP server is embedded in the same asyncio daemon and binds to loopback. We do not start a second Telethon client for Claude Code because multiple processes sharing the same Telegram session create unnecessary locking and side-effect races.

If stdio MCP compatibility is needed later, it should be a thin local proxy to the existing daemon, not another Telegram owner.

## Current layers

### `TelegramService`

Shared application service used by MCP/workflows for:

- dialogs and unread chats;
- recent messages and search;
- chat metadata;
- channel scans;
- contextual reply generation;
- explicit sends and audit logging.

### MCP adapter

MCP is a thin control surface over application services. It should not contain Telegram business logic.

Current categories:

```text
Read/research
  tg_status
  tg_list_dialogs
  tg_unread_chats
  tg_get_messages
  tg_search_messages
  tg_chat_info
  tg_generate_reply
  tg_scan_channel
  tg_list_configured_channels

Workflow/control
  tg_list_skills
  tg_run_skill
  tg_pause_automation
  tg_resume_automation

Explicit mutation
  tg_send_message
  tg_mark_read
```

Bulk workflows default to dry-run. `MCP_ALLOW_WRITES=false` disables MCP/skill mutations while keeping research available.

### `SkillRunner`

Repeated procedures are named workflows rather than giant prompts or repeated raw tool sequences.

Current examples:

```text
unread_inbox
contact_context
telegram_search
channel_research
reply_to_chat
channel_outreach
vacancy_hunt
recent_activity
```

Claude-specific `.claude/skills/` files are a UX/orchestration layer. Business rules belong in agentTG workflows, not only in prompt text.

### Policy and HITL

Policy remains deterministic and owns:

- chat mode and trust;
- sensitive-topic gating;
- cooldowns;
- owner takeover pauses;
- global pause/resume;
- approval state;
- outreach limits/deduplication.

### SQLite

SQLite is appropriate as the source of truth for the current single-user daemon.

Current durable state includes chat settings, message/audit logs, pending actions, global runtime state, monitored channels and outreach deduplication.

## Tool strategy

Do not turn agentTG into a raw Telethon MCP wrapper.

Use three levels:

```text
1. primitives
   read/search/scan/send one explicit message

2. skills/workflows
   reply, inbox triage, outreach, vacancy hunt, follow-up

3. persistent watches
   "следи за...", schedules, conditions and long-running automation
```

The current primitive tool count is acceptable. Prefer adding a high-level workflow over adding many low-value Telegram CRUD tools.

## Next architecture: durable automation

The missing capability is persistence across Claude turns/sessions.

Target flow:

```text
Telethon event ----\
MCP command --------+--> EventQueue --> WorkflowRunner --> Policy --> ActionExecutor --> Telegram
Scheduler/timer ----+
Control bot --------+
```

### `EventQueue`

Every asynchronous trigger should first become a durable event.

Suggested fields:

```text
EventQueue
- id
- kind
- source
- payload_json
- dedup_key
- status: queued | running | done | failed
- attempts
- available_at
- created_at / started_at / completed_at
- last_error
```

Principles:

- persist before processing;
- replay unfinished/retryable events on startup;
- deduplicate before side effects;
- keep previous attempts for audit.

The in-memory asyncio queue, if used, should only wake workers. SQLite remains the source of truth.

### `WorkflowRun`

Each workflow invocation should become inspectable state:

```text
WorkflowRun
- id
- workflow_name
- origin
- trigger_event_id
- status
- params_json
- result_json
- policy_profile
- started_at / finished_at
- error
```

This enables:

```text
"что сейчас работает?"
"почему этот workflow упал?"
"повтори этот run"
"покажи последние vacancy_hunt runs"
```

### `WatchRule`

Natural-language persistent intent should be stored outside Claude's conversation.

Examples:

```text
"Следи за @jobs и если появится Java backend вакансия — подготовь отклик"
"Если лид не ответил два дня — подготовь follow-up"
"Каждое утро пришли сводку новых лидов"
```

Suggested model:

```text
WatchRule
- id
- source / target
- trigger_type: telegram_event | schedule | reply_timeout
- condition
- workflow_name
- policy_profile
- limits
- enabled
- cursor / last_seen_message_id
- created_at / updated_at
```

Claude translates the user's instruction into a WatchRule once. The daemon then owns execution even after the Claude session ends.

## Event-driven first, scheduler second

Telegram already gives live events through Telethon, so new-message monitoring should be event-driven:

```text
new Telegram message -> event -> workflow
```

Do not poll Telegram every few minutes when a push-style event already exists.

Use timers/scheduler for:

- follow-up after N hours/days;
- daily/weekly digest;
- retry with backoff;
- reconciliation/catch-up;
- external sources without push events.

The scheduler should only create an event. It must not implement a separate workflow execution path.

## `ActionExecutor`: one side-effect path

Long term, all business-level Telegram writes should converge on a durable action object rather than arbitrary modules calling Telethon directly.

```text
Action
- id
- origin
- workflow_run_id
- type
- target
- payload
- policy_profile
- idempotency_key
- status: pending | executing | executed | failed | rejected
- error
- created_at / executed_at
```

`ActionExecutor` owns:

```text
claim
 -> policy/limits
 -> optional approval
 -> Telegram side effect
 -> audit
 -> success/failure state
 -> explicit retry
```

This gives MCP, automatic replies, outreach and scheduled workflows the same safety semantics.

## Capability profiles

Target permission profiles:

```text
READ_ONLY
DRAFT_ONLY
WRITE_SCOPED
AUTO_WORKFLOW
ADMIN
```

Examples:

- research-only Claude session -> `READ_ONLY`;
- normal interactive Claude -> `READ_ONLY + DRAFT_ONLY`, scoped writes after explicit instruction;
- vacancy workflow -> `AUTO_WORKFLOW` with configured channels and caps;
- administration -> explicit operator/control surface.

A future improvement is to expose fewer MCP tools to read-only clients instead of merely returning a runtime write-denied error.

## What not to add yet

Do not introduce these until the local SQLite design becomes insufficient:

- Redis/Celery/Kafka;
- Temporal;
- LangGraph for simple deterministic workflows;
- a second Telegram process just for MCP;
- dozens of raw Telegram mutation tools;
- autonomous LLM decisions that can bypass policy/caps.

Temporal and LangGraph contain useful durability/HITL concepts, but they solve a level of complexity agentTG does not yet have.

## Recommended implementation order

1. Add SQLite `EventQueue` and one worker execution path.
2. Add `WorkflowRun`, retry/backoff, dedup and startup replay.
3. Add `WatchRule` with Telegram-event, schedule and reply-timeout triggers.
4. Converge remaining business writes on `ActionExecutor`.
5. Add workflows: `inbox_triage`, `follow_up`, `daily_digest` and structured `vacancy_hunt` classification.
6. Add MCP watch/run management tools (`tg_create_watch`, `tg_list_watches`, `tg_list_runs`, `tg_retry_run`).
7. Later consider MCP resources, richer permission surfaces or an external durable workflow engine only if needed.

## Mental model

```text
Claude          = planner/operator
MCP             = control interface
Skills          = reusable procedures
WatchRules      = persistent intent
EventQueue      = durable handoff
WorkflowRunner  = orchestration
Policy          = permission boundary
ActionExecutor  = only business side-effect path
Telethon        = Telegram adapter
SQLite          = source of truth
```

The end state supports both modes without duplicating architecture:

```text
interactive:
"посмотри / найди / напиши сейчас"

autonomous:
"следи / повторяй / сделай позже / если X — сделай Y"
```
