---
description: Research a Telegram channel and, only when explicitly requested, contact people found in its posts.
disable-model-invocation: true
---

Run targeted Telegram outreach through agentTG.

1. First call `tg_run_skill` with `name="channel_outreach"` and `params.send=false` to inspect posts and extracted contacts without sending.
2. Summarize who would be contacted and why each contact appears relevant.
3. Only if the user's instruction explicitly asks to write/contact/send to people, run `channel_outreach` again with `send=true` and a conservative `max_contacts` matching the user's request.
4. Never broaden the requested channel, contact count, topic, or audience on your own.
5. Respect agentTG's configured channel policy, deduplication and rate limits. Do not bypass the workflow with repeated raw `tg_send_message` calls for bulk outreach.
6. Return sent usernames and any failures/deduplicated contacts succinctly.
