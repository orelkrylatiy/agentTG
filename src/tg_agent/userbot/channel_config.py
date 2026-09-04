"""
Channel configuration models and utilities.

# TODO: Per-Channel Customization (Feature Request)
#
# Current limitation: All channels share the same outreach prompt and action type.
#
# Desired behavior:
# ┌──────────────┬──────────────────────────┬──────────────┬─────────────┐
# │ Channel      │ Custom Prompt            │ Action Type  │ Mode        │
# ├──────────────┼──────────────────────────┼──────────────┼─────────────┤
# │ Менторство   │ "Предлагай менторство"   │ comment      │ DRAFT       │
# │ Вакансии (HR)│ "Отвечай HR кратко"      │ dm (outreach)│ AUTO        │
# │ Новости      │ —                        │ forward_only │ WATCH       │
# └──────────────┴──────────────────────────┴──────────────┴─────────────┘
#
# Required changes:
# 1. Add fields to ChannelConfig:
#    - action_type: Literal["comment", "dm", "forward_only"] = "dm"
#    - custom_prompt: str | None = None  # Override default OUTREACH_SYSTEM prompt
#    - auto_reply_mode: Literal["AUTO", "DRAFT", "WATCH"] = "DRAFT"
#
# 2. Update database schema (MonitoredChannel model):
#    - Add: action_type, custom_prompt, auto_reply_mode columns
#
# 3. Update channel_handler.py:
#    - If action_type == "comment": send reply to post (reply_to=msg.id)
#    - If action_type == "dm": current outreach flow (send to @username)
#    - If action_type == "forward_only": skip outreach, just forward
#
# 4. Update control bot commands:
#    - /channel_prompt <chat_id> <prompt>  # Set custom prompt
#    - /channel_action <chat_id> <action>  # Set action type
#
# Use cases:
# - Channel 1 (менторство): Auto-comment under posts offering mentorship
# - Channel 2 (HR vacancies): Auto-DM to recruiters with personalized reply
# - Channel 3 (news): Forward only, no auto-actions
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ChannelConfig:
    """
    Configuration for a single monitored channel.

    Attributes:
        channel_id: Numeric Telegram channel ID (e.g., -1001234567890)
        title: Human-readable channel name (for logging/UI)
        enabled: Whether to monitor this channel
        auto_outreach: Enable automatic outreach to contacts in posts
        outreach_mode: 'manual' (notify only) or 'auto' (send DMs automatically)
        keywords: Filter posts by keywords (empty = all posts)
        max_posts_per_hour: Rate limit for posts from this channel
    """

    channel_id: int
    title: str = ""
    enabled: bool = True
    auto_outreach: bool = False
    outreach_mode: Literal["manual", "auto"] = "manual"
    keywords: list[str] = field(default_factory=list)
    max_posts_per_hour: int = 60

    @classmethod
    def from_string(cls, spec: str) -> "ChannelConfig":
        """
        Parse channel specification string.

        Formats:
            - "channel_id" → minimal config
            - "channel_id:Title" → with title
            - "channel_id:Title:outreach" → with auto outreach
            - "channel_id:Title:outreach:keyword1,keyword2" → with filters

        Example:
            "-1001234567890:IT Jobs:outreach:python,frontend"
        """
        parts = spec.strip().split(":")
        if not parts:
            raise ValueError(f"Empty channel spec: {spec}")

        try:
            channel_id = int(parts[0])
        except ValueError as exc:
            raise ValueError(f"Invalid channel ID: {parts[0]}") from exc

        title = parts[1] if len(parts) > 1 and parts[1] else ""
        auto_outreach = len(parts) > 2 and parts[2].lower() == "outreach"
        keywords = []

        if len(parts) > 3 and parts[3]:
            keywords = [k.strip() for k in parts[3].split(",") if k.strip()]

        return cls(
            channel_id=channel_id,
            title=title,
            auto_outreach=auto_outreach,
            keywords=keywords,
        )

    def to_string(self) -> str:
        """Convert channel config to specification string."""
        parts = [str(self.channel_id)]
        if self.title:
            parts.append(self.title)
        if self.auto_outreach:
            parts.append("outreach")
        if self.keywords:
            parts.append(",".join(self.keywords))
        return ":".join(parts)

    def matches_keywords(self, text: str) -> bool:
        """Check if text matches configured keywords."""
        if not self.keywords:
            return True  # No filter = match all

        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in self.keywords)
