"""Exception classes for retainit."""

from typing import Any, Optional


class RetainItError(Exception):
    """Base exception for all retainit errors."""

    def __init__(self, message: str, context: Optional[dict[str, Any]] = None) -> None:
        """Initialize the exception.

        Args:
            message: The error message.
            context: Optional context information for debugging.
        """
        super().__init__(message)
        self.message = message
        self.context = context or {}


class ConfigurationError(RetainItError):
    """Raised when there's a configuration error."""


class ValidationError(RetainItError):
    """Raised when validation fails."""


class BackendError(RetainItError):
    """Raised when a backend operation fails."""


class SerializationError(RetainItError):
    """Raised when serialization/deserialization fails."""


class CacheKeyError(RetainItError):
    """Raised when there's an issue with cache key generation."""


class BackendNotAvailableError(BackendError):
    """Raised when a backend is not available or properly configured."""


class BackendConnectionError(BackendError):
    """Raised when a backend connection fails."""


class BackendTimeoutError(BackendError):
    """Raised when a backend operation times out."""


class UnsupportedDataTypeError(SerializationError):
    """Raised when trying to serialize an unsupported data type."""


class CorruptedDataError(SerializationError):
    """Raised when cached data appears to be corrupted."""


class SecurityError(RetainItError):
    """Raised when a security violation is detected."""


class CircuitBreakerOpenError(BackendError):
    """Raised when the circuit breaker is open."""
