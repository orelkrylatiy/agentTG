---
description: Research configured Telegram vacancy channels and optionally run controlled outreach.
disable-model-invocation: true
---

Use the `vacancy_hunt` agentTG workflow for vacancy-channel research.

- Start with `tg_run_skill(name="vacancy_hunt", params={"send": false})` unless the user explicitly requested immediate outreach.
- Review the returned posts and contacts; explain which channels produced useful leads.
- If the user explicitly requested outreach, rerun with `send=true` and a bounded `max_contacts`.
- Automatic sending is allowed only for channels already configured with `auto_outreach=true`; do not work around that restriction.
- Prefer a small batch first when no contact count was specified.
- Do not claim a vacancy is suitable merely because a Telegram username exists; inspect the post content.
