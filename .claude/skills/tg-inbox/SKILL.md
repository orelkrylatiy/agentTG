---
description: Review unread Telegram chats, inspect context, and summarize what needs attention.
---

Use the agentTG MCP tools to triage the owner's Telegram inbox.

1. Start with `tg_unread_chats` to get unread dialogs and recent context.
2. For ambiguous or important conversations, call `tg_get_messages` with a larger limit.
3. Summarize each chat in Russian: who wrote, what they want, urgency, and whether a reply is needed.
4. Do not send messages unless the user explicitly asks to reply or send.
5. If the user asks for a reply, use `tg_generate_reply` or draft one yourself, show the intended action clearly, then use `tg_send_message` only when sending was explicitly requested.
6. Prefer concise output and group low-priority chats together.
