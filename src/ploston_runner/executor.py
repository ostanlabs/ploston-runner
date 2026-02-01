"""Workflow executor for handling workflow/execute messages.

Handles:
- Receiving workflow execution requests from CP
- Wiring to WorkflowEngine from ploston-core
- Returning execution results
"""

import logging
from typing import TYPE_CHECKING, Any

from ploston_core.engine import ExecutionResult, WorkflowEngine
from ploston_core.invoker import ToolInvoker
from ploston_core.registry import ToolRegistry
from ploston_core.template import TemplateEngine
from ploston_core.types import ExecutionStatus
from ploston_core.workflow import WorkflowDefinition, WorkflowRegistry

from .proxy import ProxyToolInvoker

if TYPE_CHECKING:
    from .availability import AvailabilityReporter
    from .proxy import ToolProxy

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """Executes workflows on the runner using ploston-core components.

    Receives workflow/execute messages from CP, executes using the
    WorkflowEngine, and returns results.
    """

    def __init__(
        self,
        availability_reporter: "AvailabilityReporter",
        tool_proxy: "ToolProxy",
    ):
        """Initialize workflow executor.

        Args:
            availability_reporter: For accessing MCP manager
            tool_proxy: For proxying unavailable tools to CP
        """
        self._availability = availability_reporter
        self._tool_proxy = tool_proxy
        self._workflow_registry: WorkflowRegistry | None = None
        self._tool_registry: ToolRegistry | None = None
        self._tool_invoker: ToolInvoker | None = None
        self._workflow_engine: WorkflowEngine | None = None
        self._template_engine: TemplateEngine | None = None

    async def initialize(self) -> None:
        """Initialize workflow execution components."""
        logger.info("Initializing workflow executor")

        # Get MCP manager from availability reporter
        mcp_manager = self._availability.get_mcp_manager()

        # Create tool registry with MCP manager
        from ploston_core.config.models import ToolsConfig, WorkflowsConfig
        from ploston_core.invoker import SandboxFactory
        from ploston_core.mcp import MCPClientManager

        tools_config = ToolsConfig()  # Minimal config

        if mcp_manager:
            self._tool_registry = ToolRegistry(
                mcp_manager=mcp_manager,
                config=tools_config,
            )
            # Register tools from MCP manager
            await self._register_mcp_tools(mcp_manager)
            actual_mcp_manager = mcp_manager
        else:
            # Create a minimal MCP manager for the registry
            minimal_mcp_manager = MCPClientManager(config=tools_config)
            self._tool_registry = ToolRegistry(
                mcp_manager=minimal_mcp_manager,
                config=tools_config,
            )
            actual_mcp_manager = minimal_mcp_manager

        # Create workflow registry with required dependencies
        workflows_config = WorkflowsConfig(directory=".")  # Minimal config
        self._workflow_registry = WorkflowRegistry(
            tool_registry=self._tool_registry,
            config=workflows_config,
        )

        # Create template engine
        self._template_engine = TemplateEngine()

        # Create sandbox factory for tool invoker
        sandbox_factory = SandboxFactory()

        # Create base tool invoker with all required dependencies
        base_tool_invoker = ToolInvoker(
            tool_registry=self._tool_registry,
            mcp_manager=actual_mcp_manager,
            sandbox_factory=sandbox_factory,
        )

        # Wrap with ProxyToolInvoker for hybrid workflow support
        # This allows the runner to proxy unavailable tools to CP
        self._tool_invoker = ProxyToolInvoker(
            local_invoker=base_tool_invoker,
            tool_proxy=self._tool_proxy,
        )

        # Create workflow engine with proxy-enabled invoker
        from ploston_core.config.models import ExecutionConfig

        execution_config = ExecutionConfig()

        self._workflow_engine = WorkflowEngine(
            workflow_registry=self._workflow_registry,
            tool_invoker=self._tool_invoker,
            template_engine=self._template_engine,
            config=execution_config,
        )

        logger.info("Workflow executor initialized")

    async def _register_mcp_tools(self, mcp_manager: Any) -> None:
        """Register tools from MCP manager into tool registry.

        Args:
            mcp_manager: MCPClientManager instance
        """
        if not self._tool_registry:
            return

        # Get all tools from MCP manager
        all_tools = mcp_manager.list_all_tools()

        for tool in all_tools:
            self._tool_registry.register(tool)

        logger.info(f"Registered {len(all_tools)} tools from MCP servers")

    async def handle_workflow_execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle workflow/execute message from Control Plane.

        Args:
            params: Message params containing workflow definition and inputs

        Returns:
            Response dict with execution result
        """
        logger.info("Received workflow execution request")

        if not self._workflow_engine:
            return {
                "status": "error",
                "error": {
                    "code": "EXECUTOR_NOT_INITIALIZED",
                    "message": "Workflow executor not initialized",
                },
            }

        try:
            # Extract workflow definition and inputs
            workflow_dict = params.get("workflow")
            inputs = params.get("inputs", {})
            execution_id = params.get("execution_id")

            if not workflow_dict:
                return {
                    "status": "error",
                    "error": {
                        "code": "INVALID_PARAMS",
                        "message": "Missing workflow definition",
                    },
                }

            # Parse workflow definition
            workflow = self._parse_workflow(workflow_dict)

            # Register workflow temporarily
            self._workflow_registry.register(workflow)

            # Execute workflow
            result = await self._workflow_engine.execute(
                workflow_id=workflow.id,
                inputs=inputs,
            )

            # Convert result to dict
            return self._result_to_dict(result, execution_id)

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            return {
                "status": "error",
                "error": {
                    "code": "EXECUTION_FAILED",
                    "message": str(e),
                },
            }

    def _parse_workflow(self, workflow_dict: dict[str, Any]) -> WorkflowDefinition:
        """Parse workflow definition from dict.

        Args:
            workflow_dict: Raw workflow definition

        Returns:
            WorkflowDefinition instance
        """
        # WorkflowDefinition uses 'name' as identifier, not 'id'
        # The 'id' from CP is used for tracking, 'name' is the workflow name
        return WorkflowDefinition(
            name=workflow_dict.get("name", workflow_dict.get("id", "runner-workflow")),
            version=workflow_dict.get("version", "1.0.0"),
            description=workflow_dict.get("description"),
        )

    def _result_to_dict(
        self,
        result: ExecutionResult,
        execution_id: str | None,
    ) -> dict[str, Any]:
        """Convert ExecutionResult to response dict.

        Args:
            result: Workflow execution result
            execution_id: Original execution ID from CP

        Returns:
            Response dict
        """
        return {
            "status": "success" if result.status == ExecutionStatus.COMPLETED else "error",
            "execution_id": execution_id,
            "result": {
                "status": result.status.value,
                "outputs": result.outputs,
                "duration_ms": result.duration_ms,
                "steps_completed": len([s for s in result.steps if s.status.value == "completed"]),
                "steps_total": len(result.steps),
            },
            "error": {
                "code": result.error.code if result.error else None,
                "message": str(result.error) if result.error else None,
            }
            if result.error
            else None,
        }

    async def handle_tool_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tool/call message from Control Plane.

        This is for when CP orchestrates and needs to call a tool on the runner.

        Args:
            params: Message params containing tool name and arguments

        Returns:
            Response dict with tool call result
        """
        logger.info("Received tool call request")

        if not self._tool_invoker:
            return {
                "status": "error",
                "error": {
                    "code": "EXECUTOR_NOT_INITIALIZED",
                    "message": "Tool invoker not initialized",
                },
            }

        try:
            tool_name = params.get("tool")
            tool_args = params.get("args", {})

            if not tool_name:
                return {
                    "status": "error",
                    "error": {
                        "code": "INVALID_PARAMS",
                        "message": "Missing tool name",
                    },
                }

            # Check if tool is available locally
            if not self._availability.is_tool_available(tool_name):
                return {
                    "status": "error",
                    "error": {
                        "code": "TOOL_UNAVAILABLE",
                        "message": f"Tool '{tool_name}' is not available on this runner",
                    },
                }

            # Invoke tool
            result = await self._tool_invoker.invoke(
                tool_name=tool_name,
                params=tool_args,
            )

            return {
                "status": "success",
                "result": result,
            }

        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            return {
                "status": "error",
                "error": {
                    "code": "TOOL_FAILED",
                    "message": str(e),
                },
            }
