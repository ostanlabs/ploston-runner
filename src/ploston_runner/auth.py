"""Token-based authentication for runner.

Handles:
- Token storage and retrieval
- Authentication handshake with CP
- runner/register message handling
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .types import RunnerMethods, JSONRPCRequest

logger = logging.getLogger(__name__)

# Default config directory
DEFAULT_CONFIG_DIR = Path.home() / ".ploston-runner"
TOKEN_FILE = "token"


@dataclass
class AuthConfig:
    """Authentication configuration."""
    
    token: str
    runner_name: str
    config_dir: Path = DEFAULT_CONFIG_DIR


class TokenStorage:
    """Secure token storage.
    
    Stores token in user's config directory with restricted permissions.
    """
    
    def __init__(self, config_dir: Path = DEFAULT_CONFIG_DIR):
        """Initialize token storage.
        
        Args:
            config_dir: Directory to store token file
        """
        self._config_dir = config_dir
        self._token_path = config_dir / TOKEN_FILE
    
    def store(self, token: str) -> None:
        """Store token securely.
        
        Args:
            token: Authentication token to store
        """
        # Create config directory if needed
        self._config_dir.mkdir(parents=True, exist_ok=True)
        
        # Write token with restricted permissions (owner read/write only)
        self._token_path.write_text(token)
        os.chmod(self._token_path, 0o600)
        
        logger.debug(f"Token stored at {self._token_path}")
    
    def load(self) -> str | None:
        """Load stored token.
        
        Returns:
            Token string if exists, None otherwise
        """
        if not self._token_path.exists():
            return None
        
        return self._token_path.read_text().strip()
    
    def delete(self) -> None:
        """Delete stored token."""
        if self._token_path.exists():
            self._token_path.unlink()
            logger.debug("Token deleted")
    
    def exists(self) -> bool:
        """Check if token exists.
        
        Returns:
            True if token file exists
        """
        return self._token_path.exists()


class Authenticator:
    """Handles authentication with Control Plane.
    
    Manages the authentication handshake and runner registration.
    """
    
    def __init__(
        self,
        token: str,
        runner_name: str,
    ):
        """Initialize authenticator.
        
        Args:
            token: Authentication token
            runner_name: Name of this runner
        """
        self._token = token
        self._runner_name = runner_name
        self._authenticated = False
    
    @property
    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return self._authenticated
    
    @property
    def runner_name(self) -> str:
        """Get runner name."""
        return self._runner_name
    
    def create_register_request(self, request_id: int) -> JSONRPCRequest:
        """Create runner/register request message.
        
        Args:
            request_id: Request ID for the message
            
        Returns:
            JSONRPCRequest for registration
        """
        return JSONRPCRequest(
            id=request_id,
            method=RunnerMethods.REGISTER,
            params={
                "token": self._token,
                "name": self._runner_name,
            },
        )
    
    def handle_register_response(self, response: dict[str, Any]) -> bool:
        """Handle registration response from CP.
        
        Args:
            response: JSON-RPC response from CP
            
        Returns:
            True if registration successful
            
        Raises:
            AuthenticationError: If registration failed
        """
        if "error" in response:
            error = response["error"]
            error_code = error.get("code", -1)
            error_message = error.get("message", "Unknown error")
            
            logger.error(f"Registration failed: {error_message} (code: {error_code})")
            self._authenticated = False
            raise AuthenticationError(error_message, error_code)
        
        result = response.get("result", {})
        if result.get("status") == "ok":
            self._authenticated = True
            logger.info(f"Runner '{self._runner_name}' registered successfully")
            return True
        
        logger.warning(f"Unexpected registration response: {result}")
        self._authenticated = False
        return False
    
    def reset(self) -> None:
        """Reset authentication state."""
        self._authenticated = False


class AuthenticationError(Exception):
    """Authentication failed."""
    
    def __init__(self, message: str, code: int = -1):
        super().__init__(message)
        self.code = code


def hash_token(token: str) -> str:
    """Hash a token for storage/comparison.
    
    Args:
        token: Plain text token
        
    Returns:
        SHA256 hash of token
    """
    return hashlib.sha256(token.encode()).hexdigest()


def validate_token_format(token: str) -> bool:
    """Validate token format.
    
    Expected format: ploston_runner_<random>
    
    Args:
        token: Token to validate
        
    Returns:
        True if token format is valid
    """
    if not token:
        return False
    
    if not token.startswith("ploston_runner_"):
        return False
    
    # Token should have some random part after prefix
    suffix = token[len("ploston_runner_"):]
    if len(suffix) < 8:
        return False
    
    return True
