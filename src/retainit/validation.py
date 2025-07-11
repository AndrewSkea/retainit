"""Validation utilities for retainit."""

import logging
import re
from typing import Any, Callable

from .exceptions import CacheKeyError, ValidationError

logger = logging.getLogger(__name__)

# Cache key validation patterns
VALID_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9:._-]+$")
MAX_KEY_LENGTH = 250  # Redis limit is 512 bytes, but we're conservative
MIN_KEY_LENGTH = 1

# TTL validation
MIN_TTL = 1  # 1 second
MAX_TTL = 2147483647  # 2^31 - 1 seconds (about 68 years)

# Size limits for cached values
MAX_VALUE_SIZE = 100 * 1024 * 1024  # 100MB default limit
DEFAULT_VALUE_SIZE_LIMIT = 1 * 1024 * 1024  # 1MB default


def validate_cache_key(key: str) -> None:
    """Validate a cache key.

    Args:
        key: The cache key to validate.

    Raises:
        CacheKeyError: If the key is invalid.
    """
    if not isinstance(key, str):
        raise CacheKeyError(
            f"Cache key must be a string, got {type(key).__name__}",
            context={"key_type": type(key).__name__},
        )

    if len(key) < MIN_KEY_LENGTH:
        raise CacheKeyError(
            f"Cache key is too short (minimum {MIN_KEY_LENGTH} characters)",
            context={"key_length": len(key), "key": key},
        )

    if len(key) > MAX_KEY_LENGTH:
        raise CacheKeyError(
            f"Cache key is too long (maximum {MAX_KEY_LENGTH} characters)",
            context={"key_length": len(key), "key": key[:50] + "..."},
        )

    if not VALID_KEY_PATTERN.match(key):
        raise CacheKeyError(
            f"Cache key contains invalid characters. Only alphanumeric, ':', '.', '_', '-' allowed",
            context={"key": key},
        )

    # Check for path traversal attempts
    if ".." in key or "/" in key or "\\" in key:
        raise CacheKeyError(
            f"Cache key contains potentially dangerous path characters",
            context={"key": key},
        )


def validate_ttl(ttl: int | None) -> None:
    """Validate a TTL value.

    Args:
        ttl: The TTL value to validate.

    Raises:
        ValidationError: If the TTL is invalid.
    """
    if ttl is None:
        return

    if not isinstance(ttl, int):
        raise ValidationError(
            f"TTL must be an integer or None, got {type(ttl).__name__}",
            context={"ttl_type": type(ttl).__name__, "ttl_value": ttl},
        )

    if ttl < MIN_TTL:
        raise ValidationError(
            f"TTL must be at least {MIN_TTL} seconds",
            context={"ttl": ttl, "min_ttl": MIN_TTL},
        )

    if ttl > MAX_TTL:
        raise ValidationError(
            f"TTL cannot exceed {MAX_TTL} seconds",
            context={"ttl": ttl, "max_ttl": MAX_TTL},
        )


def validate_value_size(value: Any, max_size: int = DEFAULT_VALUE_SIZE_LIMIT) -> None:
    """Validate that a value is not too large to cache.

    Args:
        value: The value to validate.
        max_size: Maximum allowed size in bytes.

    Raises:
        ValidationError: If the value is too large.
    """
    # Estimate size for common types
    estimated_size = _estimate_size(value)

    if estimated_size > max_size:
        raise ValidationError(
            f"Value is too large to cache ({estimated_size} bytes > {max_size} bytes)",
            context={
                "estimated_size": estimated_size,
                "max_size": max_size,
                "value_type": type(value).__name__,
            },
        )


def validate_function_args(
    func: Callable, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    """Validate function arguments for caching.

    Args:
        func: The function being cached.
        args: Positional arguments.
        kwargs: Keyword arguments.

    Raises:
        ValidationError: If the arguments are invalid for caching.
    """
    # Check for unhashable arguments
    for i, arg in enumerate(args):
        if not _is_cacheable_type(arg):
            logger.warning(
                f"Argument {i} of type {type(arg).__name__} may not be suitable for caching"
            )

    for key, value in kwargs.items():
        if not _is_cacheable_type(value):
            logger.warning(
                f"Keyword argument '{key}' of type {type(value).__name__} may not be suitable for caching"
            )


def validate_backend_config(config: dict[str, Any]) -> None:
    """Validate backend configuration.

    Args:
        config: The configuration dictionary to validate.

    Raises:
        ValidationError: If the configuration is invalid.
    """
    if not isinstance(config, dict):
        raise ValidationError(
            f"Backend configuration must be a dictionary, got {type(config).__name__}",
            context={"config_type": type(config).__name__},
        )

    # Validate common configuration keys
    if "ttl" in config:
        validate_ttl(config["ttl"])

    if "max_size" in config:
        max_size = config["max_size"]
        if not isinstance(max_size, int) or max_size <= 0:
            raise ValidationError(
                f"max_size must be a positive integer, got {max_size}",
                context={"max_size": max_size},
            )


def sanitize_key_component(component: str) -> str:
    """Sanitize a component that will be used in a cache key.

    Args:
        component: The component to sanitize.

    Returns:
        A sanitized version suitable for use in cache keys.
    """
    if not isinstance(component, str):
        component = str(component)

    # Replace invalid characters with underscores
    sanitized = re.sub(r"[^a-zA-Z0-9:._-]", "_", component)

    # Collapse multiple underscores
    sanitized = re.sub(r"_+", "_", sanitized)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")

    # Ensure minimum length
    if len(sanitized) < MIN_KEY_LENGTH:
        sanitized = f"key_{sanitized}"

    # Truncate if too long
    if len(sanitized) > MAX_KEY_LENGTH:
        sanitized = sanitized[: MAX_KEY_LENGTH - 4] + "_trunc"

    return sanitized


def _estimate_size(obj: Any) -> int:
    """Estimate the size of an object in bytes.

    This is a rough estimation for common Python types.

    Args:
        obj: The object to estimate.

    Returns:
        Estimated size in bytes.
    """
    if obj is None:
        return 8

    if isinstance(obj, bool):
        return 8

    if isinstance(obj, int):
        return max(8, (obj.bit_length() + 7) // 8)

    if isinstance(obj, float):
        return 8

    if isinstance(obj, str):
        return len(obj.encode("utf-8"))

    if isinstance(obj, bytes):
        return len(obj)

    if isinstance(obj, (list, tuple)):
        return sum(_estimate_size(item) for item in obj) + len(obj) * 8

    if isinstance(obj, dict):
        return (
            sum(_estimate_size(k) + _estimate_size(v) for k, v in obj.items())
            + len(obj) * 16
        )

    # For unknown types, use a conservative estimate
    try:
        import sys

        return sys.getsizeof(obj)
    except:
        return 1024  # 1KB default


def _is_cacheable_type(obj: Any) -> bool:
    """Check if an object type is suitable for caching.

    Args:
        obj: The object to check.

    Returns:
        True if the object type is suitable for caching.
    """
    # Basic types are always cacheable
    if isinstance(obj, (str, int, float, bool, bytes, type(None))):
        return True

    # Collections of cacheable types are cacheable
    if isinstance(obj, (list, tuple)):
        return all(_is_cacheable_type(item) for item in obj)

    if isinstance(obj, dict):
        return all(
            _is_cacheable_type(k) and _is_cacheable_type(v) for k, v in obj.items()
        )

    # Check if the object is hashable (likely serializable)
    try:
        hash(obj)
        return True
    except TypeError:
        return False
