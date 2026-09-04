"""Environment-backed MCP settings kept separate from core Telegram credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MCPConfig:
    """Local MCP server configuration."""

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    allow_writes: bool = True

    @classmethod
    def from_env(cls) -> "MCPConfig":
        host = os.getenv("MCP_HOST", "127.0.0.1").strip()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "MCP_HOST must be loopback-only (127.0.0.1, localhost or ::1). "
                "Use an SSH/VPN tunnel for remote access."
            )

        port = int(os.getenv("MCP_PORT", "8765"))
        if not 1 <= port <= 65535:
            raise ValueError("MCP_PORT must be between 1 and 65535")

        return cls(
            enabled=_env_bool("MCP_ENABLED", True),
            host=host,
            port=port,
            allow_writes=_env_bool("MCP_ALLOW_WRITES", True),
        )
