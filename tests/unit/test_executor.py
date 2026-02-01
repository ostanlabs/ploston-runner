"""Unit tests for ploston_runner.executor module.

Tests: UT-045 to UT-058 from LOCAL_RUNNER_TEST_SPEC.md
"""

from unittest.mock import MagicMock

import pytest

from ploston_runner.executor import WorkflowExecutor


class TestWorkflowExecutor:
    """Tests for WorkflowExecutor class."""

    def test_init(self):
        """Test WorkflowExecutor initialization."""
        availability = MagicMock()
        tool_proxy = MagicMock()

        executor = WorkflowExecutor(
            availability_reporter=availability,
            tool_proxy=tool_proxy,
        )

        assert executor._availability == availability
        assert executor._tool_proxy == tool_proxy
        assert executor._workflow_engine is None

    @pytest.mark.asyncio
    async def test_handle_workflow_execute_not_initialized(self):
        """Test workflow execute when not initialized (UT-047)."""
        availability = MagicMock()
        tool_proxy = MagicMock()
        executor = WorkflowExecutor(availability, tool_proxy)

        result = await executor.handle_workflow_execute({})

        assert result["status"] == "error"
        assert result["error"]["code"] == "EXECUTOR_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_handle_workflow_execute_missing_workflow(self):
        """Test workflow execute with missing workflow (UT-047)."""
        availability = MagicMock()
        availability.get_mcp_manager.return_value = None
        tool_proxy = MagicMock()
        executor = WorkflowExecutor(availability, tool_proxy)

        # Initialize executor
        await executor.initialize()

        result = await executor.handle_workflow_execute({"inputs": {}})

        assert result["status"] == "error"
        assert result["error"]["code"] == "INVALID_PARAMS"
        assert "Missing workflow" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_handle_tool_call_not_initialized(self):
        """Test tool call when not initialized."""
        availability = MagicMock()
        tool_proxy = MagicMock()
        executor = WorkflowExecutor(availability, tool_proxy)

        result = await executor.handle_tool_call({"tool": "test"})

        assert result["status"] == "error"
        assert result["error"]["code"] == "EXECUTOR_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_handle_tool_call_missing_tool_name(self):
        """Test tool call with missing tool name."""
        availability = MagicMock()
        availability.get_mcp_manager.return_value = None
        tool_proxy = MagicMock()
        executor = WorkflowExecutor(availability, tool_proxy)

        await executor.initialize()

        result = await executor.handle_tool_call({"args": {}})

        assert result["status"] == "error"
        assert result["error"]["code"] == "INVALID_PARAMS"
        assert "Missing tool name" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_handle_tool_call_unavailable_tool(self):
        """Test tool call for unavailable tool."""
        availability = MagicMock()
        availability.get_mcp_manager.return_value = None
        availability.is_tool_available.return_value = False
        tool_proxy = MagicMock()
        executor = WorkflowExecutor(availability, tool_proxy)

        await executor.initialize()

        result = await executor.handle_tool_call({"tool": "nonexistent"})

        assert result["status"] == "error"
        assert result["error"]["code"] == "TOOL_UNAVAILABLE"

    def test_parse_workflow(self):
        """Test parsing workflow definition (UT-046)."""
        availability = MagicMock()
        tool_proxy = MagicMock()
        executor = WorkflowExecutor(availability, tool_proxy)

        workflow_dict = {
            "id": "test-workflow",
            "name": "Test Workflow",
            "description": "A test workflow",
            "version": "1.0.0",
            "inputs": [{"name": "input1", "type": "string"}],
            "outputs": [{"name": "output1", "type": "string"}],
            "steps": [{"id": "step1", "tool": "test_tool"}],
        }

        workflow = executor._parse_workflow(workflow_dict)

        # WorkflowDefinition uses 'name' as identifier
        assert workflow.name == "Test Workflow"
        assert workflow.description == "A test workflow"
        assert workflow.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test executor initialization (UT-052)."""
        availability = MagicMock()
        availability.get_mcp_manager.return_value = None
        tool_proxy = MagicMock()
        executor = WorkflowExecutor(availability, tool_proxy)

        await executor.initialize()

        assert executor._workflow_registry is not None
        assert executor._tool_registry is not None
        assert executor._template_engine is not None
        assert executor._workflow_engine is not None


class TestWorkflowResultFormat:
    """Tests for workflow result formatting (UT-048, UT-049, UT-050)."""

    def test_result_to_dict_success(self):
        """Test converting successful result to dict (UT-048)."""
        availability = MagicMock()
        tool_proxy = MagicMock()
        executor = WorkflowExecutor(availability, tool_proxy)

        # Create mock result
        from ploston_core.types import ExecutionStatus

        mock_result = MagicMock()
        mock_result.status = ExecutionStatus.COMPLETED
        mock_result.outputs = {"result": "success"}
        mock_result.duration_ms = 100
        mock_result.steps = []
        mock_result.error = None

        result_dict = executor._result_to_dict(mock_result, "exec-123")

        assert result_dict["status"] == "success"
        assert result_dict["execution_id"] == "exec-123"
        assert result_dict["result"]["status"] == "completed"
        assert result_dict["result"]["outputs"] == {"result": "success"}

    def test_result_to_dict_failure(self):
        """Test converting failed result to dict (UT-049)."""
        availability = MagicMock()
        tool_proxy = MagicMock()
        executor = WorkflowExecutor(availability, tool_proxy)

        from ploston_core.types import ExecutionStatus

        mock_result = MagicMock()
        mock_result.status = ExecutionStatus.FAILED
        mock_result.outputs = {}
        mock_result.duration_ms = 50
        mock_result.steps = []
        mock_result.error = MagicMock()
        mock_result.error.code = "STEP_FAILED"
        mock_result.error.__str__ = lambda self: "Step execution failed"

        result_dict = executor._result_to_dict(mock_result, "exec-456")

        assert result_dict["status"] == "error"
        assert result_dict["error"] is not None
        assert result_dict["error"]["code"] == "STEP_FAILED"
