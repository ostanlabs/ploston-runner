"""Unit tests for ploston_runner.availability module.

Tests: UT-033 to UT-044 from LOCAL_RUNNER_TEST_SPEC.md
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from ploston_runner.availability import AvailabilityReporter
from ploston_runner.types import MCPAvailability, MCPConfig, MCPStatus


class TestAvailabilityReporter:
    """Tests for AvailabilityReporter class."""

    def test_init(self):
        """Test AvailabilityReporter initialization."""
        connection = MagicMock()
        reporter = AvailabilityReporter(connection=connection)

        assert reporter._connection == connection
        assert reporter._health_check_interval == 30.0
        assert reporter.available_tools == []
        assert reporter.unavailable_mcps == []

    def test_init_with_custom_interval(self):
        """Test AvailabilityReporter with custom health check interval."""
        connection = MagicMock()
        reporter = AvailabilityReporter(connection=connection, health_check_interval=60.0)

        assert reporter._health_check_interval == 60.0

    def test_available_tools_empty(self):
        """Test available_tools when no MCPs configured."""
        connection = MagicMock()
        reporter = AvailabilityReporter(connection=connection)

        assert reporter.available_tools == []

    def test_available_tools_with_mcps(self):
        """Test available_tools lists tools from available MCPs (UT-037)."""
        connection = MagicMock()
        reporter = AvailabilityReporter(connection=connection)

        # Simulate availability data
        reporter._availability = {
            "filesystem": MCPAvailability(
                name="filesystem",
                status=MCPStatus.AVAILABLE,
                tools=["fs_read", "fs_write"],
                last_checked=datetime.now(UTC),
            ),
            "docker": MCPAvailability(
                name="docker",
                status=MCPStatus.AVAILABLE,
                tools=["docker_run"],
                last_checked=datetime.now(UTC),
            ),
        }

        tools = reporter.available_tools
        assert "fs_read" in tools
        assert "fs_write" in tools
        assert "docker_run" in tools

    def test_unavailable_mcps(self):
        """Test unavailable_mcps lists unavailable MCPs (UT-038)."""
        connection = MagicMock()
        reporter = AvailabilityReporter(connection=connection)

        reporter._availability = {
            "filesystem": MCPAvailability(
                name="filesystem",
                status=MCPStatus.AVAILABLE,
                tools=["fs_read"],
                last_checked=datetime.now(UTC),
            ),
            "slack": MCPAvailability(
                name="slack",
                status=MCPStatus.UNAVAILABLE,
                error="Connection refused",
                last_checked=datetime.now(UTC),
            ),
        }

        unavailable = reporter.unavailable_mcps
        assert "slack" in unavailable
        assert "filesystem" not in unavailable

    def test_is_tool_available(self):
        """Test is_tool_available method."""
        connection = MagicMock()
        reporter = AvailabilityReporter(connection=connection)

        reporter._availability = {
            "filesystem": MCPAvailability(
                name="filesystem",
                status=MCPStatus.AVAILABLE,
                tools=["fs_read", "fs_write"],
                last_checked=datetime.now(UTC),
            ),
        }

        assert reporter.is_tool_available("fs_read") is True
        assert reporter.is_tool_available("fs_write") is True
        assert reporter.is_tool_available("nonexistent") is False

    def test_mcp_config_to_server_def_http(self):
        """Test converting HTTP MCP config to server definition."""
        connection = MagicMock()
        reporter = AvailabilityReporter(connection=connection)

        config = MCPConfig(
            name="remote",
            url="http://localhost:8080/mcp",
            command="",  # Empty for HTTP transport
        )

        server_def = reporter._mcp_config_to_server_def(config)

        assert server_def.url == "http://localhost:8080/mcp"
        assert server_def.transport == "http"

    def test_mcp_config_to_server_def_stdio(self):
        """Test converting stdio MCP config to server definition."""
        connection = MagicMock()
        reporter = AvailabilityReporter(connection=connection)

        config = MCPConfig(
            name="filesystem",
            command="npx",
            args=["-y", "@mcp/filesystem"],
            env={"NODE_ENV": "production"},
        )

        server_def = reporter._mcp_config_to_server_def(config)

        assert "npx" in server_def.command
        assert "@mcp/filesystem" in server_def.command
        assert server_def.transport == "stdio"
        assert server_def.env == {"NODE_ENV": "production"}

    def test_get_mcp_manager_none(self):
        """Test get_mcp_manager returns None when not initialized."""
        connection = MagicMock()
        reporter = AvailabilityReporter(connection=connection)

        assert reporter.get_mcp_manager() is None

    @pytest.mark.asyncio
    async def test_stop(self):
        """Test stopping availability reporter."""
        connection = MagicMock()
        reporter = AvailabilityReporter(connection=connection)

        # Should not raise even when not started
        await reporter.stop()

        assert reporter._should_run is False


class TestMCPAvailability:
    """Tests for MCPAvailability dataclass."""

    def test_create_available(self):
        """Test creating available MCP status (UT-033)."""
        avail = MCPAvailability(
            name="filesystem",
            status=MCPStatus.AVAILABLE,
            tools=["fs_read", "fs_write"],
            last_checked=datetime.now(UTC),
        )

        assert avail.name == "filesystem"
        assert avail.status == MCPStatus.AVAILABLE
        assert len(avail.tools) == 2

    def test_create_unavailable(self):
        """Test creating unavailable MCP status (UT-034, UT-035)."""
        avail = MCPAvailability(
            name="slack",
            status=MCPStatus.UNAVAILABLE,
            error="Connection timeout",
            last_checked=datetime.now(UTC),
        )

        assert avail.name == "slack"
        assert avail.status == MCPStatus.UNAVAILABLE
        assert avail.error == "Connection timeout"


class TestMCPStatus:
    """Tests for MCPStatus enum."""

    def test_status_values(self):
        """Test MCPStatus enum values."""
        assert MCPStatus.AVAILABLE.value == "available"
        assert MCPStatus.UNAVAILABLE.value == "unavailable"
        assert MCPStatus.UNKNOWN.value == "unknown"
