"""Tests for local MCP runtime configuration."""

import pytest

from tg_agent.mcp_config import MCPConfig


def test_mcp_config_defaults(monkeypatch):
    for name in ("MCP_ENABLED", "MCP_HOST", "MCP_PORT", "MCP_ALLOW_WRITES"):
        monkeypatch.delenv(name, raising=False)

    config = MCPConfig.from_env()

    assert config.enabled is True
    assert config.host == "127.0.0.1"
    assert config.port == 8765
    assert config.allow_writes is True


def test_mcp_config_can_disable_writes(monkeypatch):
    monkeypatch.setenv("MCP_ALLOW_WRITES", "false")

    assert MCPConfig.from_env().allow_writes is False


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com"])
def test_mcp_rejects_non_loopback_host(monkeypatch, host):
    monkeypatch.setenv("MCP_HOST", host)

    with pytest.raises(ValueError, match="loopback-only"):
        MCPConfig.from_env()


def test_mcp_rejects_invalid_port(monkeypatch):
    monkeypatch.setenv("MCP_PORT", "70000")

    with pytest.raises(ValueError, match="between 1 and 65535"):
        MCPConfig.from_env()
