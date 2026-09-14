---
description: Draft or send a context-aware Telegram reply to a specific person or chat.
---

Handle one Telegram conversation through agentTG.

1. Resolve the target with `tg_chat_info` when needed and read enough recent history with `tg_get_messages` to understand the conversation.
2. If the user supplied exact final message text (for example an explicit quoted message), preserve that text and use `tg_send_message` only if the user asked to send it.
3. Otherwise, do not write the final Telegram copy yourself. Convert the user's request into a short intent/instruction and call `tg_generate_reply(chat=..., instructions=...)`. agentTG owns the final wording, persona and Telegram style.
4. Examples of useful `instructions`: `скажи что завтра после шести удобно`, `вежливо откажись, сейчас не ищу`, `скажи что вакансия интересна и спроси можно ли скинуть резюме`.
5. If the user asked only to draft, return the generated draft and do not send anything.
6. If the user explicitly asked to write, send, answer, reply, or tell that person something, send the generated draft with `tg_send_message`. Use `reply_to` when replying to a specific message is materially useful.
7. Do not invent commitments, prices, dates, experience or facts that are not supported by the conversation or the user's instruction.
8. After sending, report the target and resulting message ID briefly.
