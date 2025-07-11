"""retainit: High-Performance Function Caching Library.

retainit is a lightweight, extensible Python caching system for expensive function calls
with support for various backends and data types.

Example:
    Basic usage::

        from retainit import retain

        @retain
        def expensive_function(param):
            # Expensive operation
            return result

    Advanced usage with multiple backends::

        import retainit
        from retainit import retain, RedisConfig

        # Register a Redis backend
        retainit.register_backend(
            "main_cache",
            RedisConfig(
                url="redis://localhost:6379",
                ttl=300
            ),
            default=True
        )

        # Function-specific configuration
        @retain(backend="main_cache")
        def get_user_data(user_id):
            # Expensive API call
            return data

"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

__version__ = "0.1.0"

# Import public API
from retainit.backends.config import BackendConfigType
from retainit.core import retain  # noqa: F401
from retainit.registry import registry

# Setup logging
logger = logging.getLogger("retainit")

# Type definitions
F = TypeVar("F", bound=Callable[..., Any])


def register_backend(
    name: str, config: BackendConfigType, default: bool = False
) -> None:
    """Register a backend with the given name and configuration.

    This function registers a cache backend configuration with the registry,
    making it available for use by the @retain decorator.

    Args:
        name: The name to register the backend under.
        config: The backend configuration.
        default: Whether this backend should be the default.

    Example:
        >>> import retainit
        >>> from retainit import RedisConfig
        >>>
        >>> # Register a Redis backend
        >>> retainit.register_backend(
        ...     "session_cache",
        ...     RedisConfig(
        ...         url="redis://cache.example.com:6379",
        ...         password="secret",
        ...         ttl=3600  # 1 hour
        ...     ),
        ...     default=True
        ... )

    """
    registry.register(name, config, default)


def get_backend(name: str | None = None) -> BackendConfigType:
    """Get a backend configuration by name.

    Args:
        name: The name of the backend to get. If None, returns the default backend.

    Returns:
        The backend configuration.

    Raises:
        KeyError: If no backend with the given name exists.
        RuntimeError: If no default backend is configured and name is None.

    """
    return registry.get(name)


def set_default_backend(name: str) -> None:
    """Set the default backend.

    Args:
        name: The name of the backend to set as default.

    Raises:
        KeyError: If no backend with the given name exists.

    """
    registry.set_default(name)


def list_backends() -> dict[str, BackendConfigType]:
    """List all registered backends.

    Returns:
        A dictionary mapping backend names to configurations.

    """
    return registry.list_backends()


def remove_backend(name: str) -> None:
    """Remove a backend from the registry.

    Args:
        name: The name of the backend to remove.

    Raises:
        KeyError: If no backend with the given name exists.
        RuntimeError: If trying to remove the default backend.

    """
    registry.remove(name)


def clear_backends() -> None:
    """Clear all backends from the registry."""
    registry.clear()
