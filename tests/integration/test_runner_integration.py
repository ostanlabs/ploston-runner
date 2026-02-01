"""Integration tests for ploston-runner with MockControlPlane.

Tests the runner components against a mock CP to verify:
- Runner connects and registers with mock CP
- Runner receives config push and applies it
- Runner reports tool availability
- Runner executes workflows sent by mock CP
- Runner proxies tool calls to mock CP
"""

import asyncio

import pytest

from ploston_runner.availability import AvailabilityReporter
from ploston_runner.connection import RunnerConnection
from ploston_runner.proxy import ToolProxy
from ploston_runner.types import RunnerConfig, RunnerMCPConfig

from ..mocks import MockControlPlane

# Use a different port for each test to avoid conflicts
BASE_PORT = 19000


class TestRunnerConnectionIntegration:
    """Integration tests for runner connection to mock CP."""

    @pytest.mark.asyncio
    async def test_runner_connects_and_registers(self):
        """Test that runner can connect and register with mock CP."""
        port = BASE_PORT + 1

        async with MockControlPlane(port=port) as cp:
            cp.expect_registration("test-runner", "test-token-123")

            config = RunnerConfig(
                control_plane_url=f"ws://localhost:{port}",
                auth_token="test-token-123",
                runner_name="test-runner",
                heartbeat_interval=60.0,  # Long interval to avoid noise
            )

            connection = RunnerConnection(config)

            try:
                await connection.connect()

                # Verify connection is established
                assert connection.is_connected

                # Verify CP received registration
                registered = await cp.wait_for_registration(timeout=2.0)
                assert registered

            finally:
                await connection.disconnect()

    @pytest.mark.asyncio
    async def test_runner_registration_fails_with_wrong_token(self):
        """Test that registration fails with invalid token."""
        port = BASE_PORT + 2

        async with MockControlPlane(port=port) as cp:
            cp.expect_registration("test-runner", "correct-token")

            config = RunnerConfig(
                control_plane_url=f"ws://localhost:{port}",
                auth_token="wrong-token",
                runner_name="test-runner",
            )

            connection = RunnerConnection(config)

            with pytest.raises(ConnectionError, match="Authentication failed"):
                await connection.connect()

    @pytest.mark.asyncio
    async def test_runner_sends_heartbeats(self):
        """Test that runner sends periodic heartbeats."""
        port = BASE_PORT + 3

        async with MockControlPlane(port=port) as cp:
            cp.expect_registration("heartbeat-runner", "hb-token")

            config = RunnerConfig(
                control_plane_url=f"ws://localhost:{port}",
                auth_token="hb-token",
                runner_name="heartbeat-runner",
                heartbeat_interval=0.5,  # Fast heartbeat for testing
            )

            connection = RunnerConnection(config)

            try:
                await connection.connect()

                # Wait for a couple heartbeats
                await asyncio.sleep(1.5)

                # Verify CP received heartbeats
                assert len(cp.received_heartbeats) >= 2

            finally:
                await connection.disconnect()


class TestConfigReceiverIntegration:
    """Integration tests for config push from CP to runner."""

    @pytest.mark.asyncio
    async def test_runner_receives_config_push(self):
        """Test that runner receives and processes config push."""
        port = BASE_PORT + 10

        async with MockControlPlane(port=port) as cp:
            cp.expect_registration("config-runner", "config-token")

            # Set config to push after registration
            cp.set_config(
                {
                    "mcps": {
                        "test-mcp": {
                            "command": "echo",
                            "args": ["hello"],
                        }
                    }
                }
            )

            received_configs = []

            async def on_config_push(params):
                received_configs.append(params)
                return {"status": "ok"}

            config = RunnerConfig(
                control_plane_url=f"ws://localhost:{port}",
                auth_token="config-token",
                runner_name="config-runner",
                heartbeat_interval=60.0,
            )

            connection = RunnerConnection(
                config,
                on_config_push=on_config_push,
            )

            try:
                await connection.connect()

                # Wait for config push
                await asyncio.sleep(0.5)

                # Verify config was received
                assert len(received_configs) == 1
                assert "mcps" in received_configs[0]
                assert "test-mcp" in received_configs[0]["mcps"]

            finally:
                await connection.disconnect()


class TestAvailabilityReportingIntegration:
    """Integration tests for tool availability reporting."""

    @pytest.mark.asyncio
    async def test_runner_reports_availability_after_connect(self):
        """Test that runner reports tool availability after connecting."""
        port = BASE_PORT + 20

        async with MockControlPlane(port=port) as cp:
            cp.expect_registration("avail-runner", "avail-token")

            config = RunnerConfig(
                control_plane_url=f"ws://localhost:{port}",
                auth_token="avail-token",
                runner_name="avail-runner",
                heartbeat_interval=60.0,
            )

            connection = RunnerConnection(config)
            availability_reporter = AvailabilityReporter(
                connection,
                health_check_interval=60.0,  # Long interval
            )

            try:
                await connection.connect()

                # Initialize with empty MCP config (no MCPs)
                mcp_config = RunnerMCPConfig(mcps={})
                await availability_reporter.initialize_mcps(mcp_config)

                # Wait for availability report
                availability = await cp.wait_for_availability(timeout=2.0)

                # With no MCPs, should report empty available list
                assert "available" in availability
                assert "unavailable" in availability

            finally:
                await availability_reporter.stop()
                await connection.disconnect()


class TestToolProxyIntegration:
    """Integration tests for tool proxy functionality."""

    @pytest.mark.asyncio
    async def test_runner_proxies_tool_call_to_cp(self):
        """Test that runner can proxy tool calls to CP."""
        port = BASE_PORT + 30

        async with MockControlPlane(port=port) as cp:
            cp.expect_registration("proxy-runner", "proxy-token")

            config = RunnerConfig(
                control_plane_url=f"ws://localhost:{port}",
                auth_token="proxy-token",
                runner_name="proxy-runner",
                heartbeat_interval=60.0,
            )

            connection = RunnerConnection(config)
            availability_reporter = AvailabilityReporter(
                connection,
                health_check_interval=60.0,
            )
            tool_proxy = ToolProxy(
                connection,
                availability_reporter,
                timeout=5.0,
            )

            try:
                await connection.connect()

                # Initialize with empty MCP config
                mcp_config = RunnerMCPConfig(mcps={})
                await availability_reporter.initialize_mcps(mcp_config)

                # Proxy a tool call (tool not available locally)
                result = await tool_proxy.proxy_tool_call(
                    tool_name="cp-tool",
                    args={"input": "test-value"},
                )

                # MockControlPlane returns mock result
                assert result["tool_name"] == "cp-tool"
                assert "Mock result" in result["output"]

            finally:
                await availability_reporter.stop()
                await connection.disconnect()


class TestWorkflowExecutionIntegration:
    """Integration tests for workflow execution on runner."""

    @pytest.mark.asyncio
    async def test_runner_receives_workflow_execute(self):
        """Test that runner receives workflow/execute messages."""
        port = BASE_PORT + 40

        async with MockControlPlane(port=port) as cp:
            cp.expect_registration("workflow-runner", "workflow-token")

            received_workflows = []

            async def on_workflow_execute(params):
                received_workflows.append(params)
                return {
                    "status": "success",
                    "result": {"output": "workflow completed"},
                }

            config = RunnerConfig(
                control_plane_url=f"ws://localhost:{port}",
                auth_token="workflow-token",
                runner_name="workflow-runner",
                heartbeat_interval=60.0,
            )

            connection = RunnerConnection(
                config,
                on_workflow_execute=on_workflow_execute,
            )

            try:
                await connection.connect()

                # Queue and send a workflow
                request_id = cp.queue_workflow(
                    workflow_id="test-workflow",
                    inputs={"key": "value"},
                )
                await cp.send_queued_workflows()

                # Wait for result
                result = await cp.wait_for_result(request_id, timeout=5.0)

                # Verify workflow was received and executed
                assert len(received_workflows) == 1
                assert received_workflows[0]["workflow_id"] == "test-workflow"
                assert received_workflows[0]["inputs"] == {"key": "value"}

                # Verify result was sent back
                assert result.get("result", {}).get("status") == "success"

            finally:
                await connection.disconnect()

    @pytest.mark.asyncio
    async def test_runner_handles_tool_call_from_cp(self):
        """Test that runner handles tool/call messages from CP."""
        port = BASE_PORT + 41

        async with MockControlPlane(port=port) as cp:
            cp.expect_registration("tool-runner", "tool-token")

            received_tool_calls = []

            async def on_tool_call(params):
                received_tool_calls.append(params)
                return {
                    "status": "success",
                    "result": f"Executed {params.get('tool')}",
                }

            config = RunnerConfig(
                control_plane_url=f"ws://localhost:{port}",
                auth_token="tool-token",
                runner_name="tool-runner",
                heartbeat_interval=60.0,
            )

            connection = RunnerConnection(
                config,
                on_tool_call=on_tool_call,
            )

            try:
                await connection.connect()

                # Send tool/call from CP
                await cp.runner_ws.send(
                    '{"jsonrpc": "2.0", "id": 1, "method": "tool/call", "params": {"tool": "local-tool", "args": {"x": 1}}}'
                )

                # Wait for response
                await asyncio.sleep(0.5)

                # Verify tool call was received
                assert len(received_tool_calls) == 1
                assert received_tool_calls[0]["tool"] == "local-tool"
                assert received_tool_calls[0]["args"] == {"x": 1}

            finally:
                await connection.disconnect()


class TestReconnectionIntegration:
    """Integration tests for reconnection behavior."""

    @pytest.mark.asyncio
    async def test_runner_status_changes_on_disconnect(self):
        """Test that runner status changes when disconnected."""
        port = BASE_PORT + 50

        async with MockControlPlane(port=port) as cp:
            cp.expect_registration("reconnect-runner", "reconnect-token")

            config = RunnerConfig(
                control_plane_url=f"ws://localhost:{port}",
                auth_token="reconnect-token",
                runner_name="reconnect-runner",
                heartbeat_interval=60.0,
                reconnect_delay=0.5,  # Fast reconnect for testing
            )

            connection = RunnerConnection(config)

            try:
                await connection.connect()
                assert connection.is_connected

                # Disconnect
                await connection.disconnect()
                assert not connection.is_connected

            finally:
                if connection.is_connected:
                    await connection.disconnect()
