"""Tests for exception classes."""

import pytest

from retainit.exceptions import (
    BackendConnectionError,
    BackendError,
    BackendNotAvailableError,
    BackendTimeoutError,
    CacheKeyError,
    CircuitBreakerOpenError,
    ConfigurationError,
    CorruptedDataError,
    RetainItError,
    SecurityError,
    SerializationError,
    UnsupportedDataTypeError,
    ValidationError,
)


class TestRetainItError:
    """Test base exception class."""

    def test_basic_exception(self):
        """Test basic exception creation."""
        error = RetainItError("test message")
        assert str(error) == "test message"
        assert error.message == "test message"
        assert error.context == {}

    def test_exception_with_context(self):
        """Test exception with context."""
        context = {"key": "value", "number": 42}
        error = RetainItError("test message", context)
        assert error.context == context

    def test_inheritance(self):
        """Test that all custom exceptions inherit from RetainItError."""
        exceptions = [
            ConfigurationError,
            ValidationError,
            BackendError,
            SerializationError,
            CacheKeyError,
            BackendNotAvailableError,
            BackendConnectionError,
            BackendTimeoutError,
            UnsupportedDataTypeError,
            CorruptedDataError,
            SecurityError,
            CircuitBreakerOpenError,
        ]

        for exc_class in exceptions:
            error = exc_class("test")
            assert isinstance(error, RetainItError)
            assert isinstance(error, Exception)


class TestSpecificExceptions:
    """Test specific exception types."""

    def test_configuration_error(self):
        """Test configuration error."""
        error = ConfigurationError("Invalid config", {"setting": "invalid"})
        assert "Invalid config" in str(error)
        assert error.context["setting"] == "invalid"

    def test_validation_error(self):
        """Test validation error."""
        error = ValidationError("Invalid input")
        assert isinstance(error, RetainItError)

    def test_backend_error(self):
        """Test backend error."""
        error = BackendError("Backend failed")
        assert isinstance(error, RetainItError)

    def test_serialization_error(self):
        """Test serialization error."""
        error = SerializationError("Serialization failed")
        assert isinstance(error, RetainItError)

    def test_cache_key_error(self):
        """Test cache key error."""
        error = CacheKeyError("Invalid key")
        assert isinstance(error, RetainItError)

    def test_backend_not_available_error(self):
        """Test backend not available error."""
        error = BackendNotAvailableError("Backend not available")
        assert isinstance(error, BackendError)

    def test_backend_connection_error(self):
        """Test backend connection error."""
        error = BackendConnectionError("Connection failed")
        assert isinstance(error, BackendError)

    def test_backend_timeout_error(self):
        """Test backend timeout error."""
        error = BackendTimeoutError("Operation timed out")
        assert isinstance(error, BackendError)

    def test_unsupported_data_type_error(self):
        """Test unsupported data type error."""
        error = UnsupportedDataTypeError("Unsupported type")
        assert isinstance(error, SerializationError)

    def test_corrupted_data_error(self):
        """Test corrupted data error."""
        error = CorruptedDataError("Data corrupted")
        assert isinstance(error, SerializationError)

    def test_security_error(self):
        """Test security error."""
        error = SecurityError("Security violation")
        assert isinstance(error, RetainItError)

    def test_circuit_breaker_open_error(self):
        """Test circuit breaker open error."""
        error = CircuitBreakerOpenError("Circuit breaker open")
        assert isinstance(error, BackendError)
