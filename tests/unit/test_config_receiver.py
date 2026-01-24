"""Unit tests for ploston_runner.config_receiver module."""

import os
import pytest
from unittest.mock import AsyncMock

from ploston_runner.config_receiver import ConfigReceiver, ENV_VAR_PATTERN
from ploston_runner.types import MCPConfig, RunnerMCPConfig


class TestEnvVarPattern:
    """Tests for environment variable pattern matching."""

    def test_matches_valid_env_vars(self):
        """Test pattern matches valid env var references."""
        assert ENV_VAR_PATTERN.search("${HOME}")
        assert ENV_VAR_PATTERN.search("${MY_VAR}")
        assert ENV_VAR_PATTERN.search("${_PRIVATE}")
        assert ENV_VAR_PATTERN.search("${VAR123}")

    def test_does_not_match_invalid(self):
        """Test pattern doesn't match invalid references."""
        assert not ENV_VAR_PATTERN.search("$HOME")  # Missing braces
        assert not ENV_VAR_PATTERN.search("${123VAR}")  # Starts with number
        assert not ENV_VAR_PATTERN.search("${}")  # Empty


class TestConfigReceiver:
    """Tests for ConfigReceiver class."""

    def test_init(self):
        """Test ConfigReceiver initialization."""
        receiver = ConfigReceiver()
        assert receiver.current_config is None
        assert receiver.list_mcp_names() == []

    def test_init_with_callback(self):
        """Test ConfigReceiver with callback."""
        callback = AsyncMock()
        receiver = ConfigReceiver(on_config_received=callback)
        assert receiver._on_config_received == callback

    def test_resolve_env_vars_simple(self):
        """Test resolving simple env var."""
        receiver = ConfigReceiver()
        os.environ["TEST_VAR"] = "test_value"
        
        try:
            result = receiver._resolve_env_vars("prefix_${TEST_VAR}_suffix")
            assert result == "prefix_test_value_suffix"
        finally:
            del os.environ["TEST_VAR"]

    def test_resolve_env_vars_multiple(self):
        """Test resolving multiple env vars."""
        receiver = ConfigReceiver()
        os.environ["VAR1"] = "one"
        os.environ["VAR2"] = "two"
        
        try:
            result = receiver._resolve_env_vars("${VAR1} and ${VAR2}")
            assert result == "one and two"
        finally:
            del os.environ["VAR1"]
            del os.environ["VAR2"]

    def test_resolve_env_vars_missing(self):
        """Test resolving missing env var keeps original."""
        receiver = ConfigReceiver()
        result = receiver._resolve_env_vars("${NONEXISTENT_VAR_12345}")
        assert result == "${NONEXISTENT_VAR_12345}"

    def test_resolve_env_dict(self):
        """Test resolving env dict."""
        receiver = ConfigReceiver()
        os.environ["TEST_HOME"] = "/home/user"

        try:
            env = {"PATH": "/usr/bin", "HOME_DIR": "${TEST_HOME}/data"}
            result = receiver._resolve_env_dict(env)
            assert result["PATH"] == "/usr/bin"
            assert result["HOME_DIR"] == "/home/user/data"
        finally:
            del os.environ["TEST_HOME"]

    def test_parse_mcp_config_stdio(self):
        """Test parsing stdio MCP config."""
        receiver = ConfigReceiver()
        config_dict = {
            "command": "npx",
            "args": ["-y", "@anthropic/mcp-server-filesystem"],
            "env": {"NODE_ENV": "production"},
        }
        
        result = receiver._parse_mcp_config("filesystem", config_dict)
        
        assert isinstance(result, MCPConfig)
        assert result.name == "filesystem"
        assert result.command == "npx"
        assert result.args == ["-y", "@anthropic/mcp-server-filesystem"]
        assert result.env == {"NODE_ENV": "production"}
        assert result.url is None

    def test_parse_mcp_config_http(self):
        """Test parsing HTTP MCP config."""
        receiver = ConfigReceiver()
        config_dict = {
            "url": "http://localhost:8080/mcp",
        }
        
        result = receiver._parse_mcp_config("remote", config_dict)
        
        assert result.name == "remote"
        assert result.url == "http://localhost:8080/mcp"
        assert result.command == ""

    @pytest.mark.asyncio
    async def test_handle_config_push_success(self):
        """Test handling config push message."""
        callback = AsyncMock()
        receiver = ConfigReceiver(on_config_received=callback)
        
        params = {
            "mcps": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@anthropic/mcp-server-filesystem"],
                },
                "docker": {
                    "command": "docker-mcp",
                    "args": [],
                },
            }
        }
        
        result = await receiver.handle_config_push(params)
        
        assert result["status"] == "ok"
        assert result["mcps_received"] == 2
        assert receiver.current_config is not None
        assert len(receiver.current_config.mcps) == 2
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_config_push_empty(self):
        """Test handling empty config push."""
        receiver = ConfigReceiver()
        
        result = await receiver.handle_config_push({"mcps": {}})
        
        assert result["status"] == "ok"
        assert result["mcps_received"] == 0

    def test_get_mcp_config(self):
        """Test getting specific MCP config."""
        receiver = ConfigReceiver()
        receiver._current_config = RunnerMCPConfig(mcps={
            "filesystem": MCPConfig(name="filesystem", command="npx"),
        })
        
        result = receiver.get_mcp_config("filesystem")
        assert result is not None
        assert result.name == "filesystem"
        
        result = receiver.get_mcp_config("nonexistent")
        assert result is None

    def test_list_mcp_names(self):
        """Test listing MCP names."""
        receiver = ConfigReceiver()
        receiver._current_config = RunnerMCPConfig(mcps={
            "filesystem": MCPConfig(name="filesystem", command="npx"),
            "docker": MCPConfig(name="docker", command="docker-mcp"),
        })
        
        names = receiver.list_mcp_names()
        assert set(names) == {"filesystem", "docker"}
