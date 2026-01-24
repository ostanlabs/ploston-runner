"""Ploston Runner - Local runner for executing workflows on your machine.

The Local Runner enables Ploston to orchestrate Edge MCPs (filesystem, docker, git, shell)
that must run on the user's machine.
"""

__version__ = "0.1.0"

from .types import (
    RunnerConfig,
    RunnerStatus,
    MCPAvailability,
    MCPStatus,
    RunnerConnectionStatus,
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCNotification,
    RunnerMethods,
    MCPConfig,
    RunnerMCPConfig,
)
from .auth import (
    Authenticator,
    AuthenticationError,
    TokenStorage,
    AuthConfig,
    validate_token_format,
)
from .heartbeat import (
    HeartbeatManager,
    HeartbeatTimeoutError,
)
from .connection import RunnerConnection
from .config_receiver import ConfigReceiver
from .availability import AvailabilityReporter
from .executor import WorkflowExecutor
from .proxy import ToolProxy

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
