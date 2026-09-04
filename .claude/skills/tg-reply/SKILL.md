---
description: Draft or send a context-aware Telegram reply to a specific person or chat.
---

Handle one Telegram conversation through agentTG.

1. Resolve the target with `tg_chat_info` when needed.
2. Read enough recent history with `tg_get_messages` to understand the conversation.
3. If useful, call `tg_generate_reply` to use agentTG's configured persona and reply prompt.
4. If the user asked only to draft, return the draft and do not send anything.
5. If the user explicitly asked to write, send, answer, reply, or tell that person something, call `tg_send_message` with the final text. Use `reply_to` when replying to a specific message is materially useful.
6. Do not invent commitments, prices, dates, or facts that are not supported by the conversation or the user's instruction.
7. After sending, report the target and resulting message ID briefly.
