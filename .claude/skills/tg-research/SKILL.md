---
description: Research Telegram chats, people, messages, and channels without sending anything.
---

Use agentTG as a read-only Telegram research surface.

- Use `tg_search_messages` for topic/person/company searches.
- Use `tg_chat_info` to resolve a username, link, or chat ID.
- Use `tg_get_messages` to inspect conversation history.
- Use `tg_scan_channel` for recent channel posts and `tg_list_configured_channels` when the user refers to monitored channels without naming one.
- Cross-check surrounding messages before drawing conclusions from one message.
- Return message IDs, chat IDs/usernames, dates, and post links when they help the user continue the task.
- Never call `tg_send_message`, mutating skills, pause/resume, or mark-read as part of research.
