"""CLI entry point for Ploston Runner.

Usage:
    ploston-runner connect --token <token> --cp-url <url> [--name <name>]
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import click
import yaml

from .availability import AvailabilityReporter
from .config_receiver import ConfigReceiver
from .connection import RunnerConnection
from .executor import WorkflowExecutor
from .proxy import ToolProxy
from .types import RunnerConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Runner:
    """Main runner class that orchestrates all components."""

    def __init__(self, config: RunnerConfig):
        """Initialize runner with configuration.

        Args:
            config: Runner configuration
        """
        self._config = config
        self._connection: RunnerConnection | None = None
        self._config_receiver: ConfigReceiver | None = None
        self._availability: AvailabilityReporter | None = None
        self._executor: WorkflowExecutor | None = None
        self._tool_proxy: ToolProxy | None = None

    async def start(self) -> None:
        """Start the runner and connect to Control Plane."""
        logger.info(f"Starting Ploston Runner '{self._config.runner_name}'")

        # Create config receiver
        self._config_receiver = ConfigReceiver(
            on_config_received=self._on_config_received,
        )

        # Create connection with handlers
        self._connection = RunnerConnection(
            config=self._config,
            on_config_push=self._config_receiver.handle_config_push,
            on_workflow_execute=self._handle_workflow_execute,
            on_tool_call=self._handle_tool_call,
        )

        # Create availability reporter
        self._availability = AvailabilityReporter(
            connection=self._connection,
            health_check_interval=self._config.health_check_interval,
        )

        # Create tool proxy
        self._tool_proxy = ToolProxy(
            connection=self._connection,
            availability_reporter=self._availability,
        )

        # Create workflow executor
        self._executor = WorkflowExecutor(
            availability_reporter=self._availability,
            tool_proxy=self._tool_proxy,
        )

        # Connect to Control Plane
        await self._connection.connect()

        logger.info("Runner started and connected to Control Plane")

    async def _on_config_received(self, config: Any) -> None:
        """Handle new configuration from CP.

        Args:
            config: RunnerMCPConfig from CP
        """
        logger.info("Processing new MCP configuration")

        # Initialize MCPs
        if self._availability:
            await self._availability.initialize_mcps(config)

        # Initialize executor
        if self._executor:
            await self._executor.initialize()

    async def _handle_workflow_execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle workflow/execute message.

        Args:
            params: Message params

        Returns:
            Response dict
        """
        if not self._executor:
            return {
                "status": "error",
                "error": {"code": "NOT_READY", "message": "Runner not ready"},
            }
        return await self._executor.handle_workflow_execute(params)

    async def _handle_tool_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tool/call message.

        Args:
            params: Message params

        Returns:
            Response dict
        """
        if not self._executor:
            return {
                "status": "error",
                "error": {"code": "NOT_READY", "message": "Runner not ready"},
            }
        return await self._executor.handle_tool_call(params)

    async def run(self) -> None:
        """Run the runner until stopped."""
        await self.start()

        # Keep running until connection closes
        if self._connection:
            await self._connection.run()

    async def stop(self) -> None:
        """Stop the runner."""
        logger.info("Stopping runner")

        if self._availability:
            await self._availability.stop()

        if self._connection:
            await self._connection.disconnect()

        logger.info("Runner stopped")


def load_config_file(path: Path) -> dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        path: Path to config file

    Returns:
        Config dict
    """
    with open(path) as f:
        return yaml.safe_load(f)


@click.group()
@click.version_option()
def cli() -> None:
    """Ploston Runner - Execute workflows on your machine."""
    pass


@cli.command()
@click.option(
    "--token",
    envvar="PLOSTON_RUNNER_TOKEN",
    help="Authentication token for Control Plane",
)
@click.option(
    "--cp-url",
    envvar="PLOSTON_CP_URL",
    help="Control Plane WebSocket URL (e.g., wss://cp.example.com/runner)",
)
@click.option(
    "--name",
    envvar="PLOSTON_RUNNER_NAME",
    help="Runner name (defaults to hostname)",
)
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file",
)
@click.option(
    "--heartbeat-interval",
    type=float,
    default=30.0,
    help="Heartbeat interval in seconds",
)
@click.option(
    "--health-check-interval",
    type=float,
    default=30.0,
    help="Health check interval in seconds",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose logging",
)
def connect(
    token: str | None,
    cp_url: str | None,
    name: str | None,
    config_file: Path | None,
    heartbeat_interval: float,
    health_check_interval: float,
    verbose: bool,
) -> None:
    """Connect to Control Plane and start executing workflows."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load config from file if provided
    file_config: dict[str, Any] = {}
    if config_file:
        file_config = load_config_file(config_file)

    # Merge config sources (CLI > env > file)
    final_token = token or file_config.get("auth_token")
    final_url = cp_url or file_config.get("control_plane")
    final_name = name or file_config.get("runner_name")

    # Use hostname as default name
    if not final_name:
        import socket

        final_name = socket.gethostname()

    # Validate required config
    if not final_token:
        click.echo(
            "Error: Authentication token required (--token or PLOSTON_RUNNER_TOKEN)", err=True
        )
        sys.exit(1)

    if not final_url:
        click.echo("Error: Control Plane URL required (--cp-url or PLOSTON_CP_URL)", err=True)
        sys.exit(1)

    # Create config
    config = RunnerConfig(
        control_plane_url=final_url,
        auth_token=final_token,
        runner_name=final_name,
        heartbeat_interval=heartbeat_interval,
        health_check_interval=health_check_interval,
    )

    # Create and run runner
    runner = Runner(config)

    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down...")
        asyncio.run(runner.stop())
    except Exception as e:
        logger.error(f"Runner error: {e}")
        sys.exit(1)


@cli.command()
def version() -> None:
    """Show version information."""
    from . import __version__

    click.echo(f"ploston-runner {__version__}")


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
