# Research: patterns for Telegram agents, MCP tools and persistent automation

Date: 2026-09-11

This note captures architecture lessons from comparable Telegram MCP projects, agent daemons, durable workflow systems and Claude Code itself. The goal is not to copy one project, but to decide what agentTG should become next.

## Executive conclusion

The current agentTG direction is sound: **one long-running daemon owns the Telethon session, MCP is only an adapter, application services own Telegram logic, and deterministic policy owns side effects.**

The next major feature should **not** be another large batch of MCP tools. The missing layer is persistent automation:

```text
Telegram event / timer / MCP command
              |
              v
         Trigger/Event
              |
              v
      durable SQLite queue
              |
              v
         WorkflowRun
              |
              v
     policy + limits + HITL
              |
              v
         ActionExecutor
              |
              v
           Telegram
```

Target UX:

```text
"Посмотри этот канал"                 -> interactive MCP research
"Напиши этому человеку"              -> scoped explicit write
"Каждый день проверяй..."             -> scheduled workflow
"Следи за каналом и если появится..." -> persistent WatchRule
"Если он не ответит за 2 дня..."      -> durable timer/follow-up
```

## Projects and patterns reviewed

### 1. `gsamat/telegram-access-for-claude`

Source: https://github.com/gsamat/telegram-access-for-claude

Approach:

- Telegram user account via MTProto/Telethon;
- intentionally read-only MCP surface;
- only dialog/history/search/info tools exist;
- no send/edit/delete tools at all;
- recommends a separate server if write capabilities are ever needed;
- disables update/read-receipt behavior for safer research.

Lesson for agentTG:

**Capability shape is stronger than prompt safety.** If a session is supposed to research only, hiding write capabilities is cleaner than exposing `send` and asking the model not to use it.

Recommendation: later add capability profiles such as `READ_ONLY`, `DRAFT_ONLY`, `WRITE_SCOPED`, `AUTO_WORKFLOW`, and expose only the relevant MCP surface where practical.

### 2. `dryeab/mcp-telegram`

Source: https://github.com/dryeab/mcp-telegram

Approach:

- broad primitive Telegram MCP API;
- send/edit/delete/history/search/drafts/media download;
- Claude/Cursor launches the MCP server directly;
- Telethon session belongs to that MCP process;
- documentation explicitly warns about multiple processes sharing one Telethon session and `database is locked` errors.

Lesson for agentTG:

This is convenient as a generic Telegram toolbox, but it is **not** the direction we want for autonomous business workflows. Exposing every low-level Telegram mutation increases tool-selection ambiguity and makes policy harder to centralize.

Recommendation: keep agentTG's primitive MCP API relatively small. Add high-level workflows instead of `edit/delete/join/leave/...` unless a concrete use case requires them.

### 3. `yashok111/telegram-mcp`

Source: https://github.com/yashok111/telegram-mcp

Approach:

- one persistent daemon owns Telegram state;
- thin per-Claude-session MCP shim communicates with the daemon over local IPC;
- routes multiple sessions explicitly;
- has persistent background jobs, cancellation, status and access rules;
- permission prompts support temporary or permanent allow/deny decisions;
- daemon can live independently under systemd.

Lesson for agentTG:

The important pattern is **persistent daemon + thin control adapters**. The client does not own long-running state. This validates our decision to keep Telethon inside one agentTG daemon rather than spawning another Telegram client for each Claude session.

Possible future extension: if we ever need stdio MCP compatibility, implement a tiny stdio proxy to the existing daemon rather than a second Telethon owner.

### 4. `eloylp/agents`

Source: https://github.com/eloylp/agents

Relevant architecture: `docs/architecture.md`.

Approach:

- one daemon and one runtime engine;
- SQLite-backed **durable event queue** is the source of truth;
- in-memory channels are only wake-up signals;
- cron scheduler produces events, it does not run agents directly;
- HTTP, MCP, cron, webhooks and inter-agent dispatch all converge on the same event queue and execution path;
- retries create new queue records while preserving previous attempts as audit history;
- pending work is replayed after restart;
- one execution choke point prevents divergent behavior between entry surfaces.

Lesson for agentTG:

This is the closest architectural template for the next phase.

Recommendation:

```text
Telethon events ----\
MCP run_skill -------+--> EventQueue --> WorkflowRunner --> ActionExecutor
Scheduler -----------+
Control bot ---------+
```

SQLite should remain the initial source of truth. Do not introduce Redis/Celery/Kafka just to build the first durable workflow layer.

### 5. OpenHands Agent Server + Automation

Sources:

- https://github.com/OpenHands/software-agent-sdk
- https://github.com/OpenHands/automation

Approach:

- separates **agent execution** from **automation lifecycle**;
- Agent Server owns conversations, events, tools and execution;
- Automation owns scheduling, webhooks, run history and dispatch;
- clients talk to a stable server API rather than embedding execution logic everywhere.

Lesson for agentTG:

Separate concepts even if they initially live in one Python process:

```text
Telegram execution plane
  TelegramService / Policy / ActionExecutor

Automation control plane
  WatchRule / Schedule / WorkflowRun / retries / run history
```

They can remain one deployable daemon for now. The separation should be logical first, physical only if scale eventually requires it.

### 6. Huginn

Source: https://github.com/huginn/huginn

Approach:

- long-lived self-hosted watchers;
- agents create and consume events;
- trigger agents evaluate event payloads and decide whether downstream actions fire;
- scheduled checks and event-driven chains are explicit, inspectable configuration;
- dry-run is a first-class idea for trigger/action behavior.

Lesson for agentTG:

A user instruction like "следи за X и если Y — сделай Z" should become **stored configuration**, not remain only in Claude's conversation context.

Recommended domain object:

```text
WatchRule
- id
- source/target
- trigger_type: telegram_event | schedule | reply_timeout
- condition
- workflow_name
- policy_profile
- limits
- enabled
- cursor / last_seen_message_id
- created_at / updated_at
```

### 7. Temporal

Source: https://docs.temporal.io/

Approach:

- durable execution survives crashes and infrastructure failures;
- workflows can sleep for long periods and resume;
- retries/timers/state are part of the runtime model.

Lesson for agentTG:

Temporal demonstrates what a mature durable workflow engine eventually needs: resumability, timers, retries, idempotency and run history.

Recommendation: **do not add Temporal now.** Implement the small subset we need on SQLite first. Reconsider Temporal only when workflows become numerous, distributed or operationally difficult to recover.

### 8. LangGraph persistence / interrupts

Sources:

- https://docs.langchain.com/oss/python/langgraph/persistence
- https://langchain-ai.github.io/langgraphjs/how-tos/edit-graph-state/

Approach:

- checkpoints persist graph/thread state;
- execution can interrupt for human approval and resume later;
- durable thread IDs identify resumable state.

Lesson for agentTG:

Useful conceptually for multi-step LLM workflows and HITL, but our main problem is currently **business workflow durability**, not complex graph reasoning.

Recommendation: keep deterministic Python workflows for now. Add LangGraph only if individual workflows become genuinely branching, LLM-heavy state machines that are painful to express directly.

### 9. MCP specification / Python SDK

Sources:

- https://modelcontextprotocol.io/
- https://py.sdk.modelcontextprotocol.io/

Important distinction:

- **Tools**: model chooses and invokes an action/function.
- **Resources**: application-readable context/data.
- **Prompts**: user-selectable reusable prompt templates.

The MCP specification also recommends clear human control over tool execution and allows capability/tool exposure to vary with authorization.

Lesson for agentTG:

Not every piece of context needs to become another tool. Later we can expose stable information such as configuration, monitored-channel policy or workflow/run state as MCP resources, keeping the tool list focused on actual operations.

### 10. Claude Code Skills and scheduled tasks

Sources:

- https://code.claude.com/docs/en/skills
- https://code.claude.com/docs/en/scheduled-tasks

Approach:

- skill descriptions are always discoverable but the skill body loads only when used;
- repeated procedures belong in skills instead of a giant permanent instruction file;
- `/loop` and cron tasks can re-run prompts/skills during a Claude session;
- session scheduling is intentionally limited and recurring session tasks expire after seven days;
- durable unattended scheduling should use a persistent execution environment rather than relying on one chat session.

Lesson for agentTG:

Our `.claude/skills/` direction is correct: **progressive disclosure reduces agent context/tool noise.** Claude's own scheduler is useful for temporary interactive monitoring, but it should not be the source of truth for business automation.

## What we should keep from the current agentTG design

1. **One Telethon owner.** Never let every MCP client launch its own Telegram session.
2. **Shared service layer.** MCP, control bot, live handlers and future scheduler call the same application services.
3. **Deterministic policy owns permission.** LLM generates/classifies; it does not decide whether a forbidden action becomes allowed.
4. **SQLite durable state.** Appropriate for a single-user local daemon.
5. **Dry-run by default for bulk workflows.** Keep this invariant.
6. **Skills over tool explosion.** Repeated business procedures should become named workflows/skills.

## What should change next

### A. Add a durable event queue

Minimal table:

```text
EventQueue
- id
- kind
- payload_json
- source
- dedup_key
- status: queued | running | done | failed
- attempts
- available_at
- created_at / started_at / completed_at
- last_error
```

Persist before enqueueing work. On restart, replay unfinished/retryable events.

### B. Add first-class `WorkflowRun`

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

This gives Claude and the control bot a stable answer to: "что сейчас выполняется?", "что упало?", "повтори этот run".

### C. Add `WatchRule`

This is the key capability behind natural language instructions such as:

```text
"Следи за @jobs и если появится Java backend вакансия — подготовь отклик"
"Если этот человек не ответит два дня — сделай follow-up"
"Каждое утро дай сводку по новым лидам"
```

Claude should translate the instruction once into a stored WatchRule. The daemon then owns execution independently of the Claude session.

### D. Event-driven first, scheduler second

For Telegram:

```text
new Telegram message -> event immediately
```

Do **not** poll Telegram every five minutes when Telethon already provides live events.

Use scheduler/timers for:

- follow-up after N hours/days;
- daily digest;
- periodic reconciliation/catch-up;
- retry with backoff;
- sources that cannot push events.

The scheduler should only **emit an event** into the same queue. It should never contain a second execution path.

### E. Converge all writes on one `ActionExecutor`

Eventually no module should call `client.send_message()` as an independent business side effect.

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
- status
- error
- created_at / executed_at
```

`ActionExecutor` owns claim -> policy -> execute -> audit -> retry state.

This is more important than adding more LLM sophistication.

## MCP/tool strategy

Current tool count is acceptable. Do not aggressively expand it.

Use three levels:

```text
1. primitives
   get messages, search, send one message, scan channel

2. skills/workflows
   inbox triage, reply, outreach, vacancy hunt, follow-up

3. persistent watches
   "следи за...", schedules, conditions, long-running automation
```

Potential future MCP additions should be high-value control-plane operations rather than Telegram CRUD:

```text
tg_create_watch
tg_list_watches
tg_pause_watch
tg_delete_watch

tg_list_runs
tg_get_run
tg_retry_run
```

Avoid adding low-value primitives until needed:

```text
join_chat
leave_chat
edit_any_message
delete_any_message
raw_telethon_call
```

## Recommended near-term roadmap

### Phase 1 — durable automation foundation

- `EventQueue` in SQLite;
- `WorkflowRun`;
- one worker/runner path;
- retry/backoff + dedup;
- startup replay;
- run/list/retry APIs.

### Phase 2 — Watch Engine

- `WatchRule`;
- Telegram-event trigger;
- schedule/timer trigger;
- reply-timeout trigger;
- CRUD through MCP/control plane;
- bounded conditions and policy profiles.

### Phase 3 — useful business workflows

- `inbox_triage`;
- `follow_up`;
- `daily_digest`;
- improved `vacancy_hunt` with structured LLM classification;
- later tutoring variants: lead hunt, trial-booking follow-up, payment reminder, parent follow-up.

### Phase 4 — only if complexity demands it

- MCP resources for read-heavy state;
- richer capability profiles / separate read-write surfaces;
- structured workflow definitions;
- external durable engine such as Temporal;
- LangGraph for genuinely complex LLM state machines.

## Final recommendation

Do **not** turn agentTG into a giant MCP wrapper around Telethon.

Turn it into a small durable automation platform where Telegram is the first execution channel:

```text
Claude = planner/operator
MCP = control interface
Skills = reusable procedures
WatchRules = persistent intent
EventQueue = durable handoff
WorkflowRunner = orchestration
Policy = permission boundary
ActionExecutor = the only side-effect path
Telethon = Telegram adapter
SQLite = source of truth
```

That architecture gives us both modes we want:

1. interactive: "посмотри / найди / напиши сейчас";
2. autonomous: "следи / повторяй / сделай позже / если произойдёт X — выполни Y".
