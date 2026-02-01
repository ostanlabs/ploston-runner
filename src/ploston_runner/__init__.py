"""Ploston Runner - Local runner for executing workflows on your machine.

The Local Runner enables Ploston to orchestrate Edge MCPs (filesystem, docker, git, shell)
that must run on the user's machine.
"""

__version__ = "0.1.0"

from .auth import (
    AuthConfig,
    AuthenticationError,
    Authenticator,
    TokenStorage,
    validate_token_format,
)
from .availability import AvailabilityReporter
from .config_receiver import ConfigReceiver
from .connection import RunnerConnection
from .executor import WorkflowExecutor
from .heartbeat import (
    HeartbeatManager,
    HeartbeatTimeoutError,
)
from .proxy import ToolProxy
from .types import (
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    MCPAvailability,
    MCPConfig,
    MCPStatus,
    RunnerConfig,
    RunnerConnectionStatus,
    RunnerMCPConfig,
    RunnerMethods,
    RunnerStatus,
)

__all__ = [
    "__version__",
    # Types
    "RunnerConfig",
    "RunnerStatus",
    "MCPAvailability",
    "MCPStatus",
    "RunnerConnectionStatus",
    "JSONRPCMessage",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCNotification",
    "RunnerMethods",
    "MCPConfig",
    "RunnerMCPConfig",
    # Auth
    "Authenticator",
    "AuthenticationError",
    "TokenStorage",
    "AuthConfig",
    "validate_token_format",
    # Heartbeat
    "HeartbeatManager",
    "HeartbeatTimeoutError",
    # Components
    "RunnerConnection",
    "ConfigReceiver",
    "AvailabilityReporter",
    "WorkflowExecutor",
    "ToolProxy",
]
