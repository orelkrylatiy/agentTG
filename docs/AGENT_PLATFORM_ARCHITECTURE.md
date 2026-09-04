# AgentTG target architecture: automation + MCP execution plane

## Goal

AgentTG should be one reliable Telegram execution core that can be controlled from:

1. the existing Telegram control bot;
2. scheduled/recurrent workflows;
3. a local or remote AI agent through MCP;
4. CLI/dev commands.

These entry points must reuse the same application services, policy checks, idempotency and audit trail. They must not call Telethon directly.

## Architectural rule

**LLMs decide wording and semantic interpretation. Deterministic code decides permissions and side effects.**

A message received from Telegram is untrusted input. Neither an internal LLM nor an external MCP client may expand its own permissions because of instructions contained in a message.

## Layers

```text
                         ┌──────────────────────┐
                         │   Claude / AI agent  │
                         └──────────┬───────────┘
                                    │ MCP
       ┌──────────────┐     ┌──────▼───────┐     ┌────────────────┐
       │ Control Bot  │     │  MCP adapter │     │ Scheduler/CLI  │
       └──────┬───────┘     └──────┬───────┘     └───────┬────────┘
              │                    │                     │
              └──────────────┬─────┴──────────────┬──────┘
                             ▼                    ▼
                     ┌─────────────────────────────────┐
                     │       Application services      │
                     │ Chat / Messaging / Outreach /   │
                     │ Scan / Workflow / Action        │
                     └───────────────┬─────────────────┘
                                     │
                       ┌─────────────▼──────────────┐
                       │ Policy + Action execution │
                       │ approval / caps / audit   │
                       └─────────────┬──────────────┘
                                     │
                  ┌──────────────────┼─────────────────┐
                  ▼                  ▼                 ▼
              Telethon            SQLite             LLM
             Telegram I/O       durable state    text/classify
```

This is a ports-and-adapters / hexagonal shape: application logic is reusable; Telegram, MCP, aiogram, scheduler and CLI are adapters.

## Application services to extract

### `ChatService`

- list/get chats;
- get recent messages;
- change mode/trust through policy-authorized operations;
- expose unread/recent conversation state.

### `MessagingService`

- create a draft;
- prepare an outbound action;
- send/approve/reject through one action executor;
- record origin and audit metadata;
- enforce idempotency.

### `ChannelScanService`

- list configured channels;
- fetch recent posts;
- apply deterministic keyword/coarse filters;
- return compact structured posts;
- optionally hand candidates to a semantic classifier.

### `OutreachService`

- classify candidate vacancy/lead;
- deduplicate contacts/posts;
- generate a personalized draft;
- enforce per-channel/global caps;
- execute only under the workflow's permission profile;
- persist attempts and outcomes.

### `WorkflowService`

- load a named workflow/skill;
- create a `WorkflowRun`;
- execute bounded steps;
- persist progress/results/errors;
- make retries idempotent.

## Action model

All write operations should converge on a durable action object rather than calling Telethon from arbitrary code.

Suggested fields:

```text
Action
- id
- type
- origin: control_bot | mcp | workflow | auto_reply | cli
- origin_run_id
- chat_id / target
- payload
- status: pending | executing | executed | failed | rejected | expired
- approval_mode
- policy_profile
- idempotency_key
- created_at / executed_at
- error
```

For network side effects, claim the action before sending and make retries explicit.

## MCP interface

MCP should be a thin adapter over application services, not a second implementation of Telegram logic.

### Read-only tools

- `tg_get_status()`
- `tg_list_chats(mode?, limit?)`
- `tg_get_recent_messages(chat_id, limit)`
- `tg_list_channels()`
- `tg_scan_channel(channel_id, limit, include_filtered=false)`
- `tg_get_pending_actions()`
- `tg_get_outreach_history(...)`

### Draft/prepare tools

- `tg_draft_reply(chat_id, instructions?)`
- `tg_prepare_message(chat_id, text)`
- `tg_prepare_outreach(channel_id, post_id)`

These are safe defaults for an interactive external agent.

### Side-effect tools

- `tg_send_prepared_action(action_id)`
- `tg_send_message(chat_id, text, idempotency_key)`
- `tg_run_outreach(workflow_name, ...)`
- `tg_set_chat_mode(chat_id, mode)`
- `tg_set_trusted(chat_id, trusted)`
- `tg_pause()` / `tg_resume()`

The MCP server itself must enforce permissions. A client prompt cannot override them.

## MCP transport

### Same machine as Claude/Claude Code

Use **stdio**. The client spawns the AgentTG MCP process. Benefits:

- no listening network port;
- no separate HTTP auth layer;
- simple local configuration;
- good fit for Claude Code and similar desktop/local agents.

The MCP process should connect to the already-running AgentTG core through a stable application boundary. For an MVP it may import the service layer directly if process ownership is clear; a later version can use a small local IPC/API boundary.

### AgentTG on a VPS

Use **Streamable HTTP** behind strong authentication and preferably a private network/VPN. Do not expose a raw Telegram write surface publicly.

## Workflows / skills

Repeated automation should be represented as named, versioned workflow definitions rather than arbitrary cron prompts.

Example:

```yaml
name: vacancy_hunt
trigger:
  type: interval
  minutes: 10
policy_profile: vacancy_outreach
limits:
  max_sends_per_run: 5
  max_sends_per_day: 30
steps:
  - scan_channels
  - classify_vacancies
  - extract_contacts
  - deduplicate
  - generate_outreach
  - execute_or_queue_for_approval
```

The same workflow can be started via:

```text
scheduler -> vacancy_hunt
CLI       -> agenttg skill run vacancy_hunt
bot       -> /skill vacancy_hunt
MCP       -> run_skill(name="vacancy_hunt")
```

The source of truth stays in AgentTG rather than being duplicated as Claude-only prompt text.

Claude-specific skills/slash commands can still provide a convenient UX, but they should call MCP tools or `run_skill` rather than reimplement business rules.

## Suggested initial workflows

### `vacancy_hunt`

1. fetch new configured channel posts;
2. deterministic dedup/coarse keyword filter;
3. structured LLM classification (`relevant`, `score`, `role`, `company`, `contact`, `reason`);
4. policy thresholds/caps;
5. generate personalized outreach;
6. draft or send depending on workflow permission profile;
7. persist result.

### `inbox_triage`

1. collect new incoming conversations;
2. classify intent/risk;
3. prepare replies;
4. AUTO only for explicitly allowed low-risk chats; otherwise create pending actions.

### `follow_up`

1. find sent outreach without a reply after a configured interval;
2. check that no newer conversation invalidates the follow-up;
3. prepare one bounded follow-up;
4. enforce attempt count and cooldown;
5. send or request approval.

### `daily_digest`

Summarize new leads, replies, pending approvals, failed actions and workflow results for the owner.

## LLM responsibilities

Use LLMs for:

- semantic classification;
- ranking/scoring;
- concise summaries;
- natural reply/outreach generation;
- extracting structured facts from unstructured posts.

Prefer typed/structured outputs (Pydantic/JSON schema) for machine decisions.

Do **not** use an LLM to decide whether it is allowed to send, bypass a cap, mark a chat trusted, or override an approval policy.

## Permission profiles

Suggested capability levels:

```text
READ_ONLY
DRAFT_ONLY
WRITE_SCOPED
AUTO_WORKFLOW
ADMIN
```

Examples:

- local Claude default: READ_ONLY + DRAFT_ONLY;
- explicitly trusted interactive session: WRITE_SCOPED;
- `vacancy_hunt`: AUTO_WORKFLOW with channel allowlist and send caps;
- admin operations: control bot/explicit operator only.

## Security controls

- treat Telegram/channel text as untrusted content;
- no raw arbitrary Telethon object/tool exposure through MCP;
- allowlists for chats/channels/workflows where automatic writes are permitted;
- global and per-target send caps;
- idempotency keys for every side effect;
- action/workflow audit with origin;
- dry-run mode for workflows;
- persisted retry state;
- no credentials in Git;
- redact secrets and sensitive message content from logs where possible.

## Recommended implementation order

1. Finish hardening current runtime and state model.
2. Extract reusable application services from aiogram/Telethon handlers.
3. Add read-only + draft MCP tools over those services.
4. Add controlled write MCP tools with capability profiles and idempotency.
5. Add `WorkflowRun` + named workflow definitions and scheduler.
6. Expose `run_skill` through MCP, control bot and CLI.
7. Add structured LLM classifiers/evals for vacancy/reply workflows.
8. If needed, add remote Streamable HTTP MCP for a VPS deployment.

The protocol is not the hard part. Reliable side effects, policy boundaries, state, idempotency, observability and safe retries are the parts worth designing carefully.
