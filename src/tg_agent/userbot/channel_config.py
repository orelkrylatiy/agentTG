"""
Channel configuration models and utilities.
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
        except ValueError:
            raise ValueError(f"Invalid channel ID: {parts[0]}")

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
