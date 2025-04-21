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

    Advanced usage with configuration::

        import retainit
        from retainit import retain

        # Configure globally
        retainit.init(
            backend="redis",
            redis_url="redis://localhost:6379",
            ttl=300
        )

        # Function-specific configuration
        @retain(ttl=60, key_prefix="user_data")
        def get_user_data(user_id):
            # Expensive API call
            return data
"""

__version__ = "0.1.0"

# Import public API
from .config import CacheBackendType
from .core import retain
from .events import (
    EventType,
    enable_prometheus_metrics,
    events,
    on,
    setup_logging_handlers,
)
from .settings import SerializerType
from .settings import init_settings as init


def init_dev(**kwargs):
    """Initialize with development settings.

    This sets up retainit with memory caching and short TTL values,
    which is suitable for development environments.

    Args:
        **kwargs: Override default development settings.

    Returns:
        The updated settings instance.
    """
    dev_settings = {
        "backend": "memory",
        "ttl": 60,  # Short TTL for development
        "log_level": "DEBUG",
    }
    
    # Override with any provided settings
    dev_settings.update(kwargs)
    
    # Setup debug logging for events by default in dev mode
    setup_logging_handlers(logging.DEBUG)
    
    return init(**dev_settings)


def init_prod(**kwargs):
    """Initialize with production settings.
    
    This sets up retainit with Redis caching and longer TTL values,
    which is suitable for production environments.
    
    Args:
        **kwargs: Override default production settings.
        
    Returns:
        The updated settings instance.
    """
    prod_settings = {
        "backend": "redis",
        "ttl": 3600,  # 1 hour TTL
        "compression": True,
        "circuit_breaker": True,
        "log_level": "INFO",
    }
    
    # Override with any provided settings
    prod_settings.update(kwargs)
    
    # Setup standard logging for events in production mode
    setup_logging_handlers(logging.INFO)
    
    return init(**prod_settings)


def init_test(**kwargs):
    """Initialize with testing settings.
    
    This sets up retainit with a no-op cache for testing purposes.
    
    Args:
        **kwargs: Override default test settings.
        
    Returns:
        The updated settings instance.
    """
    test_settings = {
        "backend": "memory",
        "ttl": 1,  # Very short TTL
        "max_size": 10,  # Small cache size
        "log_level": "DEBUG",
    }
    
    # Override with any provided settings
    test_settings.update(kwargs)
    
    return init(**test_settings)


# Import missing but needed modules
import logging
