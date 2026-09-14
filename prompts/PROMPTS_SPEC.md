# Prompt system

## Goal

agentTG owns the final wording of generated Telegram messages. Claude/MCP may decide **what** should be communicated, but when the user has not dictated exact text, the internal agentTG LLM should decide **how** to phrase it using one shared persona/style stack.

This keeps manual replies, inbox triage, automatic replies and outreach in one voice.

## Prompt layers

Every generated reply is composed from these layers:

```text
system.ru.txt
    +
persona.ru.txt
    +
style.ru.txt
    +
safety.ru.txt
    +
reply/default.txt or reply/<chat_id>.txt
```

Outreach uses the same global layers:

```text
system.ru.txt
    +
persona.ru.txt
    +
style.ru.txt
    +
safety.ru.txt
    +
outreach/default.txt or outreach/<channel_id>.txt
```

All prompt files are loaded on use, so text edits apply without restarting the daemon.

## Files

```text
prompts/
├── system.ru.txt          # base Telegram behavior
├── persona.ru.txt         # facts about the account owner
├── style.ru.txt           # shared writing voice for all outbound generation
├── safety.ru.txt          # content-level constraints; policy still decides permission
├── reply/
│   ├── default.txt
│   └── <chat_id>.txt
└── outreach/
    ├── default.txt
    └── <channel_id>.txt
```

### `persona.ru.txt`

Contains stable facts the model may use about the owner. Do not put speculative skills, current commitments or sensitive credentials here.

### `style.ru.txt`

The shared Telegram voice. Current rules intentionally prefer short, phone-like copy and discourage AI/corporate markers such as:

- long typographic dashes;
- unnecessary parentheses;
- exhaustive technology lists;
- symmetrical cover-letter structure;
- phrases such as `готов обсудить детали` when they add no value;
- repeating the other person's message or vacancy back to them.

The code also mechanically replaces `—` and `–` with a normal `-` before generated copy is sent. Parentheses are not mechanically removed because that can change meaning; they are handled at the prompt/style level.

### `safety.ru.txt`

Controls content generation only: do not invent facts, dates, money, commitments, private information, etc. It must not decide whether sending is allowed. Permission remains in deterministic policy/MCP/workflow code.

## Reply generation

`tg_generate_reply` reads the latest incoming message plus recent conversation context and runs the internal agentTG model.

It also accepts optional owner instructions:

```text
tg_generate_reply(
  chat="@alice",
  instructions="скажи что завтра после шести удобно"
)
```

The instruction describes intent, not final copy. agentTG combines it with conversation context, persona, style and safety, then returns a draft.

Recommended division of responsibility:

```text
Claude / external agent
    understand context
    decide intent
    pass instructions
          |
          v
agentTG internal LLM
    produce final Telegram wording
          |
          v
style sanitizer
          |
          v
send only if explicitly authorized
```

If the owner provides exact final text, for example `напиши: "Да, завтра после шести удобно"`, the MCP client should preserve that text instead of rewriting it through the internal model.

## Reply-specific overrides

Resolution:

```text
prompts/reply/<chat_id>.txt
        |
        | missing / empty
        v
prompts/reply/default.txt
        |
        | missing / empty
        v
hardcoded safe fallback
```

Chat-specific files should contain only behavior that differs for that contact, for example formality or relationship context. Do not duplicate the entire global style prompt there.

## Outreach-specific overrides

Resolution:

```text
prompts/outreach/<channel_id>.txt
        |
        | missing / empty
        v
prompts/outreach/default.txt
        |
        | missing / empty
        v
hardcoded safe fallback
```

Outreach prompts describe the business purpose of the first message. Shared voice still comes from `style.ru.txt`.

The current default outreach behavior is intentionally compact:

- mention one relevant vacancy detail;
- use only relevant facts from persona;
- ask whether the position is still relevant or whether a resume can be sent;
- do not repeat the full vacancy or full tech stack;
- do not automatically propose a call;
- avoid formal cover-letter language.

## Claude Code behavior

Project skills under `.claude/skills/` instruct Claude to use agentTG as the default Telegram copywriter.

For a request like:

```text
Ответь ей, что завтра после шести удобно
```

preferred flow:

```text
tg_get_messages (if more context is needed)
        ->
tg_generate_reply(
  instructions="скажи что завтра после шести удобно"
)
        ->
tg_send_message (only if the user asked to actually send)
```

Claude should not independently rewrite the final Telegram copy unless the owner explicitly asks Claude itself for an alternative wording.

## Design rule

**Intent may come from Claude. Voice belongs to agentTG. Permission belongs to deterministic code.**

That separation lets us improve one writing style once and have it apply to interactive MCP replies, automatic replies, outreach and future workflows.
