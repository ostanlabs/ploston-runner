"""MockControlPlane - Test server that simulates Control Plane for runner testing.

Implements S-189: Test Infrastructure
- MockControlPlane class
- WebSocket server for runner connections
- Registration validation
- Config push
- Workflow dispatch
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class MockControlPlane:
    """Test server that simulates Control Plane for runner testing.

    This mock CP can:
    - Accept WebSocket connections from runners
    - Validate registration credentials
    - Push configuration to runners
    - Send workflows and receive results

    Example:
        async with MockControlPlane(port=8443) as cp:
            cp.expect_registration("test-runner", "token123")
            cp.set_config({"mcps": {"mcp1": {"url": "http://localhost"}}})

            # Runner connects and registers...

            availability = await cp.wait_for_availability()
            assert "tool1" in availability["available"]

            request_id = cp.queue_workflow("workflow1", {"input": "value"})
            await cp.send_queued_workflows()

            result = await cp.wait_for_result(request_id)
            assert result["result"]["output"] == "done"
    """

    def __init__(self, host: str = "localhost", port: int = 8443):
        """Initialize MockControlPlane.

        Args:
            host: Host to bind to
            port: Port to listen on
        """
        self.host = host
        self.port = port
        self.expected_token: str | None = None
        self.expected_name: str | None = None
        self.config_to_push: dict | None = None
        self.workflows_to_send: list[dict] = []
        self.received_availability: list[dict] = []
        self.received_results: list[dict] = []
        self.received_heartbeats: list[dict] = []
        self.runner_ws: Any | None = None  # websockets.WebSocketServerProtocol
        self._server: Any | None = None
        self._registered = False

    async def start(self) -> None:
        """Start WebSocket server."""
        try:
            import websockets
        except ImportError:
            raise ImportError("websockets package required: pip install websockets")

        self._server = await websockets.serve(self._handle_connection, self.host, self.port)
        logger.info(f"MockControlPlane started on ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("MockControlPlane stopped")

    async def __aenter__(self) -> MockControlPlane:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()

    def expect_registration(self, name: str, token: str) -> None:
        """Set expected registration credentials.

        Args:
            name: Expected runner name
            token: Expected authentication token
        """
        self.expected_name = name
        self.expected_token = token

    def set_config(self, config: dict) -> None:
        """Set config to push after registration.

        Args:
            config: Configuration dict (typically {"mcps": {...}})
        """
        self.config_to_push = config

    def queue_workflow(self, workflow_id: str, inputs: dict) -> int:
        """Queue workflow to send, return request ID.

        Args:
            workflow_id: Workflow identifier
            inputs: Workflow inputs

        Returns:
            Request ID for tracking the response
        """
        request_id = len(self.workflows_to_send) + 100
        self.workflows_to_send.append(
            {"id": request_id, "workflow_id": workflow_id, "inputs": inputs}
        )
        return request_id

    async def _handle_connection(self, ws: Any, path: str = "") -> None:
        """Handle incoming WebSocket connection."""
        self.runner_ws = ws
        self._registered = False
        logger.info(f"Runner connected from {ws.remote_address}")

        try:
            async for message in ws:
                msg = json.loads(message)
                await self._handle_message(ws, msg)
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            self.runner_ws = None
            self._registered = False

    async def _handle_message(self, ws: Any, msg: dict) -> None:
        """Route incoming messages."""
        method = msg.get("method")

        if method == "runner/register":
            await self._handle_register(ws, msg)
        elif method == "runner/availability":
            self.received_availability.append(msg["params"])
            logger.info(f"Received availability: {msg['params']}")
        elif method == "runner/heartbeat":
            self.received_heartbeats.append(msg["params"])
            logger.debug(f"Received heartbeat: {msg['params']}")
        elif method == "tool/proxy":
            await self._handle_tool_proxy(ws, msg)
        elif msg.get("result") is not None or msg.get("error") is not None:
            self.received_results.append(msg)
            logger.info(f"Received result for request {msg.get('id')}")

    async def _handle_register(self, ws: Any, msg: dict) -> None:
        """Handle registration, push config if valid."""
        params = msg["params"]
        msg_id = msg.get("id")

        if params.get("token") == self.expected_token and params.get("name") == self.expected_name:
            # Success
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {"status": "ok"}}))
            self._registered = True
            logger.info(f"Runner '{params['name']}' registered successfully")

            # Push config if set
            if self.config_to_push:
                await ws.send(
                    json.dumps(
                        {"jsonrpc": "2.0", "method": "config/push", "params": self.config_to_push}
                    )
                )
                logger.info("Pushed config to runner")
        else:
            # Failure
            await ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32001, "message": "Invalid token or name"},
                    }
                )
            )
            logger.warning(f"Registration failed for '{params.get('name')}'")

    async def _handle_tool_proxy(self, ws: Any, msg: dict) -> None:
        """Handle tool/proxy request (mock response)."""
        msg_id = msg.get("id")
        params = msg.get("params", {})

        # ToolProxy sends "tool" not "tool_name"
        tool_name = params.get("tool") or params.get("tool_name")

        # Return a mock success response
        await ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"tool_name": tool_name, "output": f"Mock result for {tool_name}"},
                }
            )
        )

    async def send_workflow(self, workflow: dict) -> None:
        """Send workflow/execute to connected runner.

        Args:
            workflow: Workflow dict with id, workflow_id, inputs
        """
        if not self.runner_ws:
            raise RuntimeError("No runner connected")

        await self.runner_ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": workflow["id"],
                    "method": "workflow/execute",
                    "params": {
                        "workflow_id": workflow["workflow_id"],
                        "inputs": workflow["inputs"],
                    },
                }
            )
        )
        logger.info(f"Sent workflow {workflow['workflow_id']} (id={workflow['id']})")

    async def send_queued_workflows(self) -> None:
        """Send all queued workflows to the connected runner."""
        for workflow in self.workflows_to_send:
            await self.send_workflow(workflow)
        self.workflows_to_send.clear()

    async def wait_for_availability(self, timeout: float = 5.0) -> dict:
        """Wait for availability report.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            Availability params dict

        Raises:
            TimeoutError: If no availability received within timeout
        """
        start = time.time()
        while time.time() - start < timeout:
            if self.received_availability:
                return self.received_availability.pop(0)
            await asyncio.sleep(0.1)
        raise TimeoutError("No availability received")

    async def wait_for_result(self, request_id: int, timeout: float = 30.0) -> dict:
        """Wait for workflow result.

        Args:
            request_id: Request ID to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            Result message dict

        Raises:
            TimeoutError: If no result received within timeout
        """
        start = time.time()
        while time.time() - start < timeout:
            for result in self.received_results:
                if result.get("id") == request_id:
                    self.received_results.remove(result)
                    return result
            await asyncio.sleep(0.1)
        raise TimeoutError(f"No result for request {request_id}")

    async def wait_for_registration(self, timeout: float = 5.0) -> bool:
        """Wait for runner to register.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if registered, False if timeout
        """
        start = time.time()
        while time.time() - start < timeout:
            if self._registered:
                return True
            await asyncio.sleep(0.1)
        return False
