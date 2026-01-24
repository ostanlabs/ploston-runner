"""Unit tests for ploston_runner.heartbeat module.

Tests: UT-014 to UT-017 from LOCAL_RUNNER_TEST_SPEC.md
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from ploston_runner.heartbeat import HeartbeatManager, HeartbeatTimeoutError
from ploston_runner.types import RunnerMethods


class TestHeartbeatManager:
    """Tests for HeartbeatManager class."""

    def test_init(self):
        """Test HeartbeatManager initialization."""
        manager = HeartbeatManager(interval=30.0, timeout=10.0)
        
        assert manager.interval == 30.0
        assert not manager.is_running
        assert manager.last_sent is None
        assert manager.last_ack is None
        assert manager.consecutive_failures == 0

    def test_init_with_callback(self):
        """Test HeartbeatManager with timeout callback."""
        callback = AsyncMock()
        manager = HeartbeatManager(on_timeout=callback)
        
        assert manager._on_timeout == callback

    def test_create_heartbeat_message(self):
        """Test heartbeat message creation (UT-015)."""
        manager = HeartbeatManager()
        
        message = manager.create_heartbeat_message()
        
        assert message.method == RunnerMethods.HEARTBEAT
        assert "timestamp" in message.params

    def test_heartbeat_message_format(self):
        """Test heartbeat JSON-RPC format (UT-015)."""
        manager = HeartbeatManager()
        
        message = manager.create_heartbeat_message()
        msg_dict = message.to_dict()
        
        assert msg_dict["jsonrpc"] == "2.0"
        assert msg_dict["method"] == "runner/heartbeat"
        assert "params" in msg_dict
        assert "timestamp" in msg_dict["params"]

    def test_set_send_func(self):
        """Test setting send function."""
        manager = HeartbeatManager()
        send_func = AsyncMock()
        
        manager.set_send_func(send_func)
        
        assert manager._send_func == send_func

    @pytest.mark.asyncio
    async def test_start_without_send_func(self):
        """Test starting without send function raises error."""
        manager = HeartbeatManager()
        
        with pytest.raises(RuntimeError, match="Send function not set"):
            await manager.start()

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Test starting and stopping heartbeat loop."""
        manager = HeartbeatManager(interval=0.1)
        send_func = AsyncMock()
        manager.set_send_func(send_func)
        
        await manager.start()
        assert manager.is_running
        
        await asyncio.sleep(0.05)  # Let it run briefly
        
        await manager.stop()
        assert not manager.is_running

    @pytest.mark.asyncio
    async def test_heartbeat_interval(self):
        """Test heartbeat sent at interval (UT-014)."""
        manager = HeartbeatManager(interval=0.1)
        send_func = AsyncMock()
        manager.set_send_func(send_func)
        
        await manager.start()
        
        # Wait for at least 2 heartbeats
        await asyncio.sleep(0.25)
        
        await manager.stop()
        
        # Should have sent at least 2 heartbeats
        assert send_func.call_count >= 2

    @pytest.mark.asyncio
    async def test_heartbeat_timeout_detection(self):
        """Test heartbeat timeout triggers callback (UT-016)."""
        timeout_callback = AsyncMock()
        manager = HeartbeatManager(interval=0.05, on_timeout=timeout_callback)
        
        # Send function that always fails
        async def failing_send(msg):
            raise Exception("Connection lost")
        
        manager.set_send_func(failing_send)
        
        await manager.start()
        
        # Wait for multiple failures (3 consecutive = timeout)
        await asyncio.sleep(0.3)
        
        await manager.stop()
        
        # Timeout callback should have been called
        assert timeout_callback.called

    @pytest.mark.asyncio
    async def test_heartbeat_resume_after_reconnect(self):
        """Test heartbeat resumes after reconnect (UT-017)."""
        manager = HeartbeatManager(interval=0.1)
        send_func = AsyncMock()
        manager.set_send_func(send_func)
        
        # Start, stop, then start again
        await manager.start()
        await asyncio.sleep(0.15)
        await manager.stop()
        
        first_count = send_func.call_count
        
        # Reset and start again
        manager.reset()
        await manager.start()
        await asyncio.sleep(0.15)
        await manager.stop()
        
        # Should have sent more heartbeats
        assert send_func.call_count > first_count

    def test_acknowledge(self):
        """Test heartbeat acknowledgment."""
        manager = HeartbeatManager()
        manager._consecutive_failures = 5
        
        manager.acknowledge()
        
        assert manager.last_ack is not None
        assert manager.consecutive_failures == 0

    def test_reset(self):
        """Test resetting heartbeat state."""
        manager = HeartbeatManager()
        manager._last_sent = datetime.now(timezone.utc)
        manager._last_ack = datetime.now(timezone.utc)
        manager._consecutive_failures = 3
        
        manager.reset()
        
        assert manager.last_sent is None
        assert manager.last_ack is None
        assert manager.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_consecutive_failures_tracking(self):
        """Test consecutive failure counting."""
        manager = HeartbeatManager(interval=0.05)
        
        failure_count = 0
        async def failing_send(msg):
            nonlocal failure_count
            failure_count += 1
            raise Exception("Send failed")
        
        manager.set_send_func(failing_send)
        
        await manager.start()
        await asyncio.sleep(0.2)
        await manager.stop()
        
        # Should have tracked failures
        assert manager.consecutive_failures > 0

    @pytest.mark.asyncio
    async def test_double_start_warning(self):
        """Test starting twice logs warning."""
        manager = HeartbeatManager(interval=0.1)
        send_func = AsyncMock()
        manager.set_send_func(send_func)
        
        await manager.start()
        await manager.start()  # Should not raise, just warn
        
        await manager.stop()


class TestHeartbeatTimeoutError:
    """Tests for HeartbeatTimeoutError exception."""

    def test_exception(self):
        """Test HeartbeatTimeoutError can be raised."""
        with pytest.raises(HeartbeatTimeoutError):
            raise HeartbeatTimeoutError("Heartbeat timed out")
