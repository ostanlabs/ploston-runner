"""Unit tests for ploston_runner.auth module.

Tests: UT-006 to UT-013 from LOCAL_RUNNER_TEST_SPEC.md
"""

import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from ploston_runner.auth import (
    TokenStorage,
    Authenticator,
    AuthenticationError,
    AuthConfig,
    validate_token_format,
    hash_token,
)
from ploston_runner.types import RunnerMethods


class TestTokenStorage:
    """Tests for TokenStorage class (UT-009)."""

    def test_store_and_load(self):
        """Test storing and loading token."""
        with TemporaryDirectory() as tmpdir:
            storage = TokenStorage(config_dir=Path(tmpdir))
            token = "ploston_runner_test12345"
            
            storage.store(token)
            loaded = storage.load()
            
            assert loaded == token

    def test_token_stored_securely(self):
        """Test token stored with secure permissions (UT-009)."""
        with TemporaryDirectory() as tmpdir:
            storage = TokenStorage(config_dir=Path(tmpdir))
            token = "ploston_runner_secure123"
            
            storage.store(token)
            
            # Check file permissions (0o600 = owner read/write only)
            token_path = Path(tmpdir) / "token"
            mode = token_path.stat().st_mode & 0o777
            assert mode == 0o600

    def test_load_nonexistent(self):
        """Test loading when no token exists."""
        with TemporaryDirectory() as tmpdir:
            storage = TokenStorage(config_dir=Path(tmpdir))
            
            result = storage.load()
            
            assert result is None

    def test_delete(self):
        """Test deleting token."""
        with TemporaryDirectory() as tmpdir:
            storage = TokenStorage(config_dir=Path(tmpdir))
            storage.store("ploston_runner_delete123")
            
            storage.delete()
            
            assert not storage.exists()
            assert storage.load() is None

    def test_exists(self):
        """Test checking if token exists."""
        with TemporaryDirectory() as tmpdir:
            storage = TokenStorage(config_dir=Path(tmpdir))
            
            assert not storage.exists()
            
            storage.store("ploston_runner_exists123")
            
            assert storage.exists()


class TestAuthenticator:
    """Tests for Authenticator class (UT-006, UT-007, UT-010-013)."""

    def test_init(self):
        """Test Authenticator initialization."""
        auth = Authenticator(token="ploston_runner_test123", runner_name="my-runner")
        
        assert auth.runner_name == "my-runner"
        assert not auth.is_authenticated

    def test_create_register_request(self):
        """Test creating register request (UT-010, UT-013)."""
        auth = Authenticator(token="ploston_runner_test123", runner_name="my-runner")
        
        request = auth.create_register_request(request_id=1)
        
        assert request.method == RunnerMethods.REGISTER
        assert request.id == 1
        assert request.params["token"] == "ploston_runner_test123"
        assert request.params["name"] == "my-runner"

    def test_register_message_format(self):
        """Test register message JSON-RPC format (UT-010)."""
        auth = Authenticator(token="ploston_runner_test123", runner_name="my-runner")
        
        request = auth.create_register_request(request_id=42)
        msg = request.to_dict()
        
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "runner/register"
        assert msg["id"] == 42
        assert "params" in msg

    def test_handle_register_response_ok(self):
        """Test successful registration (UT-006, UT-011)."""
        auth = Authenticator(token="ploston_runner_test123", runner_name="my-runner")
        
        response = {"result": {"status": "ok"}}
        result = auth.handle_register_response(response)
        
        assert result is True
        assert auth.is_authenticated

    def test_handle_register_response_error(self):
        """Test registration error handling (UT-007, UT-012)."""
        auth = Authenticator(token="invalid_token", runner_name="my-runner")
        
        response = {
            "error": {
                "code": -32001,
                "message": "Invalid token"
            }
        }
        
        with pytest.raises(AuthenticationError) as exc_info:
            auth.handle_register_response(response)
        
        assert "Invalid token" in str(exc_info.value)
        assert exc_info.value.code == -32001
        assert not auth.is_authenticated

    def test_handle_register_response_unexpected(self):
        """Test unexpected registration response."""
        auth = Authenticator(token="ploston_runner_test123", runner_name="my-runner")
        
        response = {"result": {"status": "unknown"}}
        result = auth.handle_register_response(response)
        
        assert result is False
        assert not auth.is_authenticated

    def test_reset(self):
        """Test resetting authentication state."""
        auth = Authenticator(token="ploston_runner_test123", runner_name="my-runner")
        auth.handle_register_response({"result": {"status": "ok"}})
        
        assert auth.is_authenticated
        
        auth.reset()
        
        assert not auth.is_authenticated


class TestTokenValidation:
    """Tests for token validation functions."""

    def test_validate_token_format_valid(self):
        """Test valid token format."""
        assert validate_token_format("ploston_runner_abcd1234")
        assert validate_token_format("ploston_runner_12345678")
        assert validate_token_format("ploston_runner_verylongrandomstring")

    def test_validate_token_format_invalid(self):
        """Test invalid token formats (UT-007)."""
        assert not validate_token_format("")
        assert not validate_token_format("invalid_token")
        assert not validate_token_format("ploston_runner_")  # No suffix
        assert not validate_token_format("ploston_runner_short")  # Too short (< 8 chars)
        assert not validate_token_format("wrong_prefix_12345678")

    def test_hash_token(self):
        """Test token hashing."""
        token = "ploston_runner_test123"
        
        hashed = hash_token(token)
        
        assert len(hashed) == 64  # SHA256 hex digest
        assert hashed == hash_token(token)  # Deterministic
        assert hashed != hash_token("different_token")


class TestAuthConfig:
    """Tests for AuthConfig dataclass."""

    def test_create_config(self):
        """Test creating auth config."""
        config = AuthConfig(
            token="ploston_runner_test123",
            runner_name="my-runner",
        )
        
        assert config.token == "ploston_runner_test123"
        assert config.runner_name == "my-runner"
