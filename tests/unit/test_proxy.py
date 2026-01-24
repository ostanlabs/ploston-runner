"""Unit tests for ploston_runner.proxy module."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from ploston_runner.proxy import ToolProxy, ProxyToolInvoker
from ploston_runner.types import RunnerMethods


@pytest.fixture
def mock_connection():
    """Create a mock connection."""
    connection = MagicMock()
    connection.is_connected = True
    connection.send_request = AsyncMock()
    return connection


@pytest.fixture
def mock_availability():
    """Create a mock availability reporter."""
    availability = MagicMock()
    availability.is_tool_available = MagicMock(return_value=False)
    return availability


class TestToolProxy:
    """Tests for ToolProxy class."""

    def test_init(self, mock_connection, mock_availability):
        """Test ToolProxy initialization."""
        proxy = ToolProxy(
            connection=mock_connection,
            availability_reporter=mock_availability,
            timeout=30.0,
        )
        
        assert proxy._connection == mock_connection
        assert proxy._availability == mock_availability
        assert proxy._timeout == 30.0

    def test_is_tool_available_locally(self, mock_connection, mock_availability):
        """Test checking local tool availability."""
        proxy = ToolProxy(mock_connection, mock_availability)
        
        mock_availability.is_tool_available.return_value = True
        assert proxy.is_tool_available_locally("fs_read") is True
        
        mock_availability.is_tool_available.return_value = False
        assert proxy.is_tool_available_locally("unknown_tool") is False

    @pytest.mark.asyncio
    async def test_proxy_tool_call_success(self, mock_connection, mock_availability):
        """Test successful tool call proxy."""
        proxy = ToolProxy(mock_connection, mock_availability)
        
        mock_connection.send_request.return_value = {
            "result": {"content": "file contents"},
        }
        
        result = await proxy.proxy_tool_call("fs_read", {"path": "/test.txt"})
        
        mock_connection.send_request.assert_called_once_with(
            RunnerMethods.TOOL_PROXY,
            {"tool": "fs_read", "args": {"path": "/test.txt"}},
            timeout=60.0,
        )
        assert result == {"content": "file contents"}

    @pytest.mark.asyncio
    async def test_proxy_tool_call_error(self, mock_connection, mock_availability):
        """Test tool call proxy with error response."""
        proxy = ToolProxy(mock_connection, mock_availability)
        
        mock_connection.send_request.return_value = {
            "error": {"code": -32002, "message": "Tool not found"},
        }
        
        result = await proxy.proxy_tool_call("unknown_tool", {})
        
        assert result["status"] == "error"
        assert result["error"]["code"] == -32002

    @pytest.mark.asyncio
    async def test_proxy_tool_call_not_connected(self, mock_connection, mock_availability):
        """Test tool call proxy when not connected."""
        proxy = ToolProxy(mock_connection, mock_availability)
        mock_connection.is_connected = False
        
        with pytest.raises(ConnectionError, match="Not connected"):
            await proxy.proxy_tool_call("fs_read", {})

    @pytest.mark.asyncio
    async def test_invoke_tool_local(self, mock_connection, mock_availability):
        """Test invoking tool locally when available."""
        proxy = ToolProxy(mock_connection, mock_availability)
        mock_availability.is_tool_available.return_value = True
        
        local_invoker = AsyncMock(return_value={"result": "local"})
        
        result = await proxy.invoke_tool(
            "fs_read",
            {"path": "/test.txt"},
            local_invoker=local_invoker,
        )
        
        local_invoker.invoke.assert_called_once_with(
            tool_name="fs_read",
            params={"path": "/test.txt"},
        )
        # Connection should not be used
        mock_connection.send_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_invoke_tool_proxy(self, mock_connection, mock_availability):
        """Test invoking tool via proxy when not available locally."""
        proxy = ToolProxy(mock_connection, mock_availability)
        mock_availability.is_tool_available.return_value = False
        
        mock_connection.send_request.return_value = {
            "result": {"content": "proxied"},
        }
        
        result = await proxy.invoke_tool("remote_tool", {"arg": "value"})
        
        mock_connection.send_request.assert_called_once()


class TestProxyToolInvoker:
    """Tests for ProxyToolInvoker class."""

    @pytest.mark.asyncio
    async def test_invoke(self, mock_connection, mock_availability):
        """Test ProxyToolInvoker.invoke."""
        tool_proxy = ToolProxy(mock_connection, mock_availability)
        local_invoker = MagicMock()
        
        proxy_invoker = ProxyToolInvoker(local_invoker, tool_proxy)
        
        mock_availability.is_tool_available.return_value = False
        mock_connection.send_request.return_value = {"result": "ok"}
        
        result = await proxy_invoker.invoke(
            tool_name="test_tool",
            params={"key": "value"},
            step_id="step-1",
            execution_id="exec-1",
        )
        
        mock_connection.send_request.assert_called_once()
