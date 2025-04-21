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
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

__version__ = "0.1.0"

# Import public API
from .backends.config import (
    BackendConfig,
    BackendConfigType,
    DiskConfig,
    DynamoDBConfig,
    MemoryConfig,
    RedisConfig,
    S3Config,
)
from .core import retain
from .events import (
    EventType,
    enable_prometheus_metrics,
    events,
    on,
    setup_logging_handlers,
)
from .registry import registry

# Setup logging
logger = logging.getLogger("retainit")

# Type definitions
F = TypeVar('F', bound=Callable[..., Any])


def register_backend(name: str, config: BackendConfigType, default: bool = False) -> None:
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


def get_backend(name: Optional[str] = None) -> BackendConfigType:
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


def list_backends() -> Dict[str, BackendConfigType]:
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


def init_dev(**kwargs: Any) -> None:
    """Initialize with development settings.

    This sets up retainit with memory caching and short TTL values,
    which is suitable for development environments.

    Args:
        **kwargs: Override default development settings for the memory backend.

    Example:
        >>> import retainit
        >>> retainit.init_dev(max_size=1000, ttl=60)
    """
    # Start with default development settings
    config = MemoryConfig(
        ttl=60,  # Short TTL for development
        max_size=1000,
        compression=False,
    )
    
    # Override with any provided settings
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    # Register the development backend
    register_backend("dev", config, default=True)
    
    # Setup debug logging for events by default in dev mode
    setup_logging_handlers(logging.DEBUG)
    
    logger.debug("Initialized development environment")


def init_prod(
    backend_type: str = "redis",
    redis_url: Optional[str] = None,
    redis_password: Optional[str] = None, 
    s3_bucket: Optional[str] = None,
    **kwargs: Any
) -> None:
    """Initialize with production settings.
    
    This sets up retainit with production-ready caching configuration,
    defaulting to Redis if no specific settings are provided.
    
    Args:
        backend_type: The backend type to use ("redis", "s3", "disk").
        redis_url: Redis connection URL when using Redis backend.
        redis_password: Redis password when using Redis backend.
        s3_bucket: S3 bucket name when using S3 backend.
        **kwargs: Additional backend-specific settings.
        
    Raises:
        ValueError: If backend_type is invalid or required settings are missing.
        
    Example:
        >>> import retainit
        >>> retainit.init_prod(
        ...     backend_type="redis",
        ...     redis_url="redis://cache.example.com:6379",
        ...     ttl=3600
        ... )
    """
    config: Union[RedisConfig, S3Config, DiskConfig] | None = None
    if backend_type == "redis":
        if not redis_url:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        
        config = RedisConfig(
            url=redis_url,
            password=redis_password,
            ttl=3600,  # 1 hour TTL
            ssl=True,
            compression=True,
        )
    elif backend_type == "s3":
        if not s3_bucket:
            s3_bucket = os.environ.get("S3_BUCKET")
            if not s3_bucket:
                raise ValueError("S3 bucket must be provided for S3 backend")
        
        config = S3Config(
            bucket=s3_bucket,
            ttl=86400,  # 1 day TTL
            compression=True,
        )
    elif backend_type == "disk":
        config = DiskConfig(
            base_path=kwargs.pop("base_path", "/tmp/retainit"),
            ttl=3600,  # 1 hour TTL
            compression=True,
        )
    else:
        raise ValueError(f"Invalid backend_type: {backend_type}")
    
    # Override with any provided settings
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    # Register the production backend
    register_backend("prod", config, default=True)
    
    # Setup standard logging for events in production mode
    setup_logging_handlers(logging.INFO)
    
    logger.info(f"Initialized production environment with {backend_type} backend")


def init_test(**kwargs: Any) -> None:
    """Initialize with testing settings.
    
    This sets up retainit with a small, fast memory cache suitable for testing.
    
    Args:
        **kwargs: Override default test settings for the memory backend.
        
    Example:
        >>> import retainit
        >>> retainit.init_test(ttl=1, max_size=5)
    """
    # Start with default test settings
    config = MemoryConfig(
        ttl=1,  # Very short TTL
        max_size=10,  # Small cache size
        compression=False,
    )
    
    # Override with any provided settings
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    # Register the test backend
    register_backend("test", config, default=True)
    
    logger.debug("Initialized test environment")


# Import missing but needed modules
import os
