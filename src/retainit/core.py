"""Core functionality for retainit.

This module contains the main `retain` decorator and related functionality
for caching function results.
"""

import asyncio
import functools
import hashlib
import inspect
import logging
import time
import traceback
from collections.abc import Awaitable, Callable
from typing import Any, Optional, ParamSpec, TypeVar, Union, cast, overload

from .backends.base import CacheBackend
from .config import CacheBackendType, config
from .events import EventType, events
from .exceptions import (
    BackendError,
    BackendNotAvailableError,
    CacheKeyError,
    RetainItError,
    ValidationError,
)
from .settings import SerializerType, settings
from .validation import validate_cache_key, validate_function_args, validate_ttl

# Setup logging
logger = logging.getLogger("retainit.core")

# Type definitions
F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")
P = ParamSpec("P")
CacheKeyType = str
CacheValueType = Any
AsyncCallable = Callable[P, Awaitable[T]]
SyncCallable = Callable[P, T]
AnyCallable = Union[AsyncCallable[P, T], SyncCallable[P, T]]


class CacheManager:
    """Manages cache operations across different backends.

    This class provides a unified interface for cache operations
    across different backend implementations.

    Attributes:
        backend: The current cache backend instance.
        ttl: Default time-to-live for cached values in seconds.

    """

    def __init__(self) -> None:
        """Initialize the cache manager."""
        self._backend: Optional[CacheBackend[Any]] = None
        self._initialized = False
        self._initialization_lock = asyncio.Lock()

    async def get(self, key: CacheKeyType, function_name: str) -> Optional[Any]:
        """Get a value from the cache.

        Args:
            key: The cache key to retrieve.
            function_name: The name of the function being cached (for events).

        Returns:
            The cached value, or None if not found.

        Raises:
            BackendError: If cache operation fails.
            ValidationError: If key is invalid.

        """
        validate_cache_key(key)
        await self._ensure_initialized()

        try:
            value = await self._backend.get(key)
            if value is not None:
                # Emit cache hit event
                await events.emit(
                    EventType.CACHE_HIT,
                    {
                        "key": key,
                        "function": function_name,
                        "backend": settings.backend.value,
                    },
                )
                logger.debug(f"Cache hit for {key}")
            else:
                # Emit cache miss event
                await events.emit(
                    EventType.CACHE_MISS,
                    {
                        "key": key,
                        "function": function_name,
                        "backend": settings.backend.value,
                    },
                )
                logger.debug(f"Cache miss for {key}")
            return value
        except Exception as e:
            error_type = type(e).__name__
            # Emit cache error event
            await events.emit(
                EventType.CACHE_ERROR,
                {
                    "key": key,
                    "function": function_name,
                    "backend": settings.backend.value,
                    "error": str(e),
                    "error_type": error_type,
                },
            )
            logger.error(f"Cache get error for {key}: {str(e)}")
            return None

    async def set(
        self,
        key: CacheKeyType,
        value: Any,
        function_name: str,
        ttl: Optional[int] = None,
    ) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key to set.
            value: The value to cache.
            function_name: The name of the function being cached (for events).
            ttl: Optional time-to-live in seconds. If None, uses the default TTL.

        Raises:
            BackendError: If cache operation fails.
            ValidationError: If inputs are invalid.

        """
        validate_cache_key(key)
        if ttl is not None:
            validate_ttl(ttl)
        await self._ensure_initialized()

        try:
            await self._backend.set(key, value, ttl or settings.ttl)
            # Emit cache set event
            await events.emit(
                EventType.CACHE_SET,
                {
                    "key": key,
                    "function": function_name,
                    "backend": settings.backend.value,
                    "ttl": ttl or settings.ttl,
                },
            )
            logger.debug(f"Cache set for {key}")
        except Exception as e:
            error_type = type(e).__name__
            # Emit cache error event
            await events.emit(
                EventType.CACHE_ERROR,
                {
                    "key": key,
                    "function": function_name,
                    "backend": settings.backend.value,
                    "error": str(e),
                    "error_type": error_type,
                    "operation": "set",
                },
            )
            logger.error(f"Cache set error for {key}: {str(e)}")

    async def delete(self, key: CacheKeyType) -> None:
        """Delete a value from the cache.

        Args:
            key: The cache key to delete.

        Raises:
            BackendError: If cache operation fails.
            ValidationError: If key is invalid.

        """
        validate_cache_key(key)
        await self._ensure_initialized()

        try:
            await self._backend.delete(key)
            # Emit cache delete event
            await events.emit(
                EventType.CACHE_DELETE,
                {
                    "key": key,
                    "backend": settings.backend.value,
                },
            )
            logger.debug(f"Cache delete for {key}")
        except Exception as e:
            # Emit cache error event
            await events.emit(
                EventType.CACHE_ERROR,
                {
                    "key": key,
                    "backend": settings.backend.value,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "operation": "delete",
                },
            )
            logger.error(f"Cache delete error for {key}: {str(e)}")

    async def clear(self) -> None:
        """Clear all values from the cache.

        Raises:
            BackendError: If cache operation fails.
        """
        await self._ensure_initialized()

        try:
            await self._backend.clear()
            # Emit cache clear event
            await events.emit(
                EventType.CACHE_CLEAR,
                {
                    "backend": settings.backend.value,
                },
            )
            logger.debug("Cache cleared")
        except Exception as e:
            # Emit cache error event
            await events.emit(
                EventType.CACHE_ERROR,
                {
                    "backend": settings.backend.value,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "operation": "clear",
                },
            )
            logger.error(f"Cache clear error: {str(e)}")

    async def _ensure_initialized(self) -> None:
        """Ensure the cache manager is initialized.

        This lazily initializes the backend when it is first used.

        Raises:
            BackendNotAvailableError: If the backend cannot be initialized.
            ValidationError: If backend configuration is invalid.

        """
        if self._initialized and self._backend is not None:
            return

        async with self._initialization_lock:
            if self._initialized and self._backend is not None:
                return

            try:
                # Initialize the configuration if not already done
                if not config.is_initialized():
                    config.init()

                # Import and initialize the appropriate backend
                backend_type = settings.backend

                if backend_type == CacheBackendType.MEMORY:
                    from .backends.memory import MemoryCache

                    self._backend = MemoryCache(max_size=settings.max_size)
                elif backend_type == CacheBackendType.DISK:
                    from .backends.disk import DiskCache

                    self._backend = DiskCache(
                        base_directory=settings.base_path,
                        compression=settings.compression,
                    )
                elif backend_type == CacheBackendType.REDIS:
                    if not settings.redis:
                        raise BackendNotAvailableError(
                            "Redis settings not configured",
                            context={"backend_type": backend_type.value},
                        )
                    try:
                        from .backends.redis import RedisCache

                        self._backend = RedisCache(
                            url=settings.redis.url,
                            password=settings.redis.password,
                            ssl=settings.redis.ssl,
                            ssl_cert_reqs=settings.redis.cert_reqs,
                            ssl_ca_certs=settings.redis.ca_certs,
                        )
                    except ImportError as e:
                        raise BackendNotAvailableError(
                            "Redis backend requires 'redis' package. "
                            "Install with 'pip install retainit[redis]'",
                            context={
                                "backend_type": backend_type.value,
                                "import_error": str(e),
                            },
                        ) from e
                elif backend_type == CacheBackendType.S3:
                    if not settings.s3:
                        raise BackendNotAvailableError(
                            "S3 settings not configured",
                            context={"backend_type": backend_type.value},
                        )
                    try:
                        from .backends.s3 import S3Cache

                        self._backend = S3Cache(
                            bucket=settings.s3.bucket,
                            prefix=settings.s3.prefix,
                            region=settings.s3.region,
                        )
                    except ImportError as e:
                        raise BackendNotAvailableError(
                            "S3 backend requires 'aioboto3' package. "
                            "Install with 'pip install retainit[aws]'",
                            context={
                                "backend_type": backend_type.value,
                                "import_error": str(e),
                            },
                        ) from e
                elif backend_type == CacheBackendType.DYNAMODB:
                    if not settings.dynamodb:
                        raise BackendNotAvailableError(
                            "DynamoDB settings not configured",
                            context={"backend_type": backend_type.value},
                        )
                    try:
                        from .backends.dynamodb import DynamoDBCache

                        self._backend = DynamoDBCache(
                            table=settings.dynamodb.table,
                            region=settings.dynamodb.region,
                        )
                    except ImportError as e:
                        raise BackendNotAvailableError(
                            "DynamoDB backend requires 'aioboto3' package. "
                            "Install with 'pip install retainit[aws]'",
                            context={
                                "backend_type": backend_type.value,
                                "import_error": str(e),
                            },
                        ) from e
                else:
                    raise BackendNotAvailableError(
                        f"Unsupported backend: {backend_type}",
                        context={"backend_type": backend_type.value},
                    )

                # Emit backend initialization event
                await events.emit(
                    EventType.BACKEND_INIT,
                    {
                        "backend": backend_type.value,
                        "settings": {
                            "ttl": settings.ttl,
                            "compression": settings.compression,
                            "max_size": settings.max_size,
                        },
                    },
                )

                self._initialized = True
                logger.info(f"Cache manager initialized with backend: {backend_type}")

            except Exception as e:
                logger.error(f"Failed to initialize cache backend {backend_type}: {e}")
                if isinstance(e, (BackendNotAvailableError, ValidationError)):
                    raise
                raise BackendNotAvailableError(
                    f"Failed to initialize cache backend: {e}",
                    context={"backend_type": backend_type.value, "error": str(e)},
                ) from e


# Create a singleton instance
cache_manager = CacheManager()


def build_cache_key(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    key_builder: Optional[Callable[..., str]] = None,
    key_prefix: Optional[str] = None,
    exclude_args: Optional[list[str]] = None,
) -> str:
    """Build a cache key from function and arguments.

    Args:
        func: The function being cached.
        args: Positional arguments to the function.
        kwargs: Keyword arguments to the function.
        key_builder: Optional custom function to build the cache key.
        key_prefix: Optional prefix for the cache key.
        exclude_args: Optional list of argument names to exclude from the key.

    Returns:
        A string cache key.

    Raises:
        CacheKeyError: If key generation fails.
        ValidationError: If inputs are invalid.

    """
    try:
        if key_builder:
            custom_key = key_builder(func, *args, **kwargs)
            if not isinstance(custom_key, str):
                raise CacheKeyError(
                    f"Custom key builder must return a string, got {type(custom_key).__name__}",
                    context={
                        "key_builder": key_builder.__name__,
                        "returned_type": type(custom_key).__name__,
                    },
                )
            validate_cache_key(custom_key)
            return custom_key

        # Default key builder uses function name and arguments
        module_name = func.__module__ or "__main__"
        func_name = func.__qualname__ or func.__name__

        # Get argument names if we need to exclude some
        arg_names: list[str] = []
        exclude_set = set(exclude_args or [])
        if exclude_set:
            try:
                sig = inspect.signature(func)
                arg_names = list(sig.parameters.keys())
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not get function signature for {func_name}: {e}")

        # Add args and kwargs to key
        arg_parts: list[str] = []

        # Process positional arguments
        for i, arg in enumerate(args):
            # Skip excluded arguments
            if exclude_set and i < len(arg_names) and arg_names[i] in exclude_set:
                continue

            try:
                # Try to use a stable hash for the arg
                arg_hash = _safe_hash(arg)
                arg_parts.append(str(arg_hash))
            except Exception as e:
                logger.warning(
                    f"Failed to hash argument {i} ({type(arg).__name__}): {e}"
                )
                # Use string representation as fallback
                arg_parts.append(_safe_str(arg))

        # Process keyword arguments
        for k, v in sorted(kwargs.items()):
            # Skip excluded arguments
            if k in exclude_set:
                continue

            try:
                value_hash = _safe_hash(v)
                arg_parts.append(f"{k}:{value_hash}")
            except Exception as e:
                logger.warning(
                    f"Failed to hash keyword argument '{k}' ({type(v).__name__}): {e}"
                )
                arg_parts.append(f"{k}:{_safe_str(v)}")

        # Create a deterministic key string
        key_str = f"{module_name}.{func_name}:{':'.join(arg_parts)}"

        # Use SHA-256 for better security and collision resistance
        key_hash = hashlib.sha256(key_str.encode("utf-8")).hexdigest()[
            :32
        ]  # Truncate for readability

        # Use specified prefix or default
        prefix = key_prefix or settings.key_prefix
        final_key = f"{prefix}:{key_hash}"

        # Validate the generated key
        validate_cache_key(final_key)
        return final_key

    except (CacheKeyError, ValidationError):
        raise
    except Exception as e:
        logger.error(f"Failed to build cache key for {func.__name__}: {e}")
        raise CacheKeyError(
            f"Failed to build cache key: {e}",
            context={
                "function": func.__name__,
                "module": getattr(func, "__module__", "unknown"),
                "error": str(e),
            },
        ) from e


def _safe_hash(obj: Any) -> int:
    """Safely hash an object, handling unhashable types.

    Args:
        obj: The object to hash.

    Returns:
        A hash value for the object.

    Raises:
        TypeError: If the object cannot be hashed.
    """
    try:
        return hash(obj)
    except TypeError:
        # For unhashable types, try to convert to a hashable representation
        if isinstance(obj, dict):
            return hash(tuple(sorted(obj.items())))
        elif isinstance(obj, list):
            return hash(tuple(obj))
        elif isinstance(obj, set):
            return hash(tuple(sorted(obj)))
        else:
            # Last resort: hash the string representation
            return hash(str(obj))


def _safe_str(obj: Any, max_length: int = 100) -> str:
    """Safely convert an object to string, handling large objects.

    Args:
        obj: The object to convert to string.
        max_length: Maximum length of the resulting string.

    Returns:
        A string representation of the object.
    """
    try:
        str_repr = str(obj)
        if len(str_repr) > max_length:
            str_repr = str_repr[:max_length] + "..."
        return str_repr
    except Exception:
        return f"<{type(obj).__name__} object>"


# Type overloads for better IDE type hints
@overload
def retain(func: F) -> F: ...


@overload
def retain(
    *,
    ttl: Optional[int] = None,
    key_builder: Optional[Callable[..., str]] = None,
    key_prefix: Optional[str] = None,
    backend: Optional[CacheBackendType] = None,
    compression: Optional[bool] = None,
    serializer: Optional[SerializerType] = None,
    exclude_args: Optional[list[str]] = None,
) -> Callable[[F], F]: ...


def retain(
    func: Optional[F] = None,
    *,
    ttl: Optional[int] = None,
    key_builder: Optional[Callable[..., str]] = None,
    key_prefix: Optional[str] = None,
    backend: Optional[CacheBackendType] = None,
    compression: Optional[bool] = None,
    serializer: Optional[SerializerType] = None,
    exclude_args: Optional[list[str]] = None,
) -> Union[F, Callable[[F], F]]:
    """Decorator that caches function results.

    This decorator can be used with both synchronous and asynchronous functions.
    It will cache the function's result based on its arguments and return the
    cached value on subsequent calls with the same arguments.

    Args:
        func: The function to decorate.
        ttl: Optional time-to-live in seconds. If None, uses the default TTL.
        key_builder: Optional function to build the cache key.
        key_prefix: Optional prefix for cache keys.
        backend: Optional override for the cache backend.
        compression: Optional override for cache compression.
        serializer: Optional override for the serializer.
        exclude_args: Optional list of argument names to exclude from the key.

    Returns:
        The decorated function with caching capabilities.

    Raises:
        ValidationError: If parameters are invalid.

    Example:
        >>> @retain
        ... def expensive_function(param):
        ...     # Expensive operation
        ...     return result

        >>> @retain(ttl=60, key_prefix="user_data")
        ... def get_user_data(user_id):
        ...     # Expensive API call
        ...     return data

    """
    # Validate parameters early
    if ttl is not None:
        validate_ttl(ttl)
    if exclude_args is not None and not isinstance(exclude_args, list):
        raise ValidationError(
            "exclude_args must be a list of strings",
            context={"exclude_args_type": type(exclude_args).__name__},
        )

    # If called without arguments, just decorate the function
    if func is not None:
        if not callable(func):
            raise ValidationError(
                "retain decorator can only be applied to callable objects",
                context={"object_type": type(func).__name__},
            )

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return _wrapped_func(func, args, kwargs)

        # Add utilities to the wrapped function
        wrapper.cache_clear = cache_manager.clear  # type: ignore
        wrapper.cache_delete = lambda *a, **kw: asyncio.create_task(  # type: ignore
            cache_manager.delete(
                build_cache_key(func, a, kw, key_builder, key_prefix, exclude_args)
            )
        )
        wrapper.cache_info = lambda: _get_cache_info(func)  # type: ignore

        return cast(F, wrapper)

    # If called with arguments, return a decorator
    def decorator(func: F) -> F:
        if not callable(func):
            raise ValidationError(
                "retain decorator can only be applied to callable objects",
                context={"object_type": type(func).__name__},
            )

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return _wrapped_func(
                func,
                args,
                kwargs,
                ttl,
                key_builder,
                key_prefix,
                backend,
                compression,
                serializer,
                exclude_args,
            )

        # Add utilities to the wrapped function
        wrapper.cache_clear = cache_manager.clear  # type: ignore
        wrapper.cache_delete = lambda *a, **kw: asyncio.create_task(  # type: ignore
            cache_manager.delete(
                build_cache_key(func, a, kw, key_builder, key_prefix, exclude_args)
            )
        )
        wrapper.cache_info = lambda: _get_cache_info(func)  # type: ignore

        return cast(F, wrapper)

    return decorator


def _get_cache_info(func: Callable[..., Any]) -> dict[str, Any]:
    """Get cache information for a function.

    Args:
        func: The cached function.

    Returns:
        Dictionary with cache information.
    """
    return {
        "function_name": func.__name__,
        "module": getattr(func, "__module__", "unknown"),
        "backend_type": settings.backend.value if settings.backend else "unknown",
        "cache_enabled": True,
    }


async def _get_cached_value(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    ttl: Optional[int] = None,
    key_builder: Optional[Callable[..., str]] = None,
    key_prefix: Optional[str] = None,
    exclude_args: Optional[list[str]] = None,
) -> tuple[bool, Any]:
    """Get a value from the cache or call the function.

    Args:
        func: The function being cached.
        args: Positional arguments to the function.
        kwargs: Keyword arguments to the function.
        ttl: Optional time-to-live in seconds.
        key_builder: Optional custom function to build the cache key.
        key_prefix: Optional prefix for the cache key.
        exclude_args: Optional list of argument names to exclude from the key.

    Returns:
        A tuple of (was_cached, value).

    Raises:
        RetainItError: If caching operations fail.

    """
    try:
        # Validate function arguments
        validate_function_args(func, args, kwargs)

        # Generate cache key
        key = build_cache_key(func, args, kwargs, key_builder, key_prefix, exclude_args)
        func_name = f"{getattr(func, '__module__', 'unknown')}.{getattr(func, '__qualname__', func.__name__)}"

        # Try to get from cache
        cached_value = await cache_manager.get(key, func_name)
        if cached_value is not None:
            return True, cached_value
    except Exception as e:
        # Log cache errors but don't fail the function call
        logger.error(f"Cache get failed for {func.__name__}: {e}")
        # Continue to function execution

    # Call the function
    try:
        # Emit function call start event
        try:
            await events.emit(
                EventType.FUNCTION_CALL_START,
                {
                    "function": func_name,
                    "key": key,
                    "args_count": len(args),
                    "kwargs_count": len(kwargs),
                },
            )
        except Exception as event_error:
            logger.warning(f"Failed to emit function start event: {event_error}")

        start_time = time.time()

        # Call the function based on whether it's async or not
        if asyncio.iscoroutinefunction(func):
            result = await func(*args, **kwargs)
        else:
            result = func(*args, **kwargs)

        duration = time.time() - start_time

        # Emit function call end event
        try:
            await events.emit(
                EventType.FUNCTION_CALL_END,
                {
                    "function": func_name,
                    "key": key,
                    "duration": duration,
                    "result_type": type(result).__name__,
                },
            )
        except Exception as event_error:
            logger.warning(f"Failed to emit function end event: {event_error}")

        # Cache the result
        try:
            await cache_manager.set(key, result, func_name, ttl)
        except Exception as cache_error:
            logger.error(f"Failed to cache result for {func_name}: {cache_error}")
            # Don't raise the cache error, return the result anyway

        return False, result

    except Exception as e:
        # Emit function error event
        try:
            await events.emit(
                EventType.FUNCTION_ERROR,
                {
                    "function": func_name,
                    "key": key,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                },
            )
        except Exception as event_error:
            logger.warning(f"Failed to emit function error event: {event_error}")

        logger.error(f"Error in function {func_name}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise


def _wrapped_func(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    ttl: Optional[int] = None,
    key_builder: Optional[Callable[..., str]] = None,
    key_prefix: Optional[str] = None,
    backend: Optional[CacheBackendType] = None,
    compression: Optional[bool] = None,
    serializer: Optional[SerializerType] = None,
    exclude_args: Optional[list[str]] = None,
) -> Any:
    """Common implementation for both sync and async functions.

    This function handles the caching logic for both synchronous and
    asynchronous functions.

    Args:
        func: The function being cached.
        args: Positional arguments to the function.
        kwargs: Keyword arguments to the function.
        ttl: Optional time-to-live in seconds.
        key_builder: Optional custom function to build the cache key.
        key_prefix: Optional prefix for the cache key.
        backend: Optional override for the cache backend.
        compression: Optional override for cache compression.
        serializer: Optional override for the serializer.
        exclude_args: Optional list of argument names to exclude from the key.

    Returns:
        The function result, either from cache or from calling the function.

    Raises:
        The original function's exceptions, plus potential caching errors.

    """
    # TODO: Handle backend, compression, and serializer overrides

    # If the function is async, return an async wrapper
    if asyncio.iscoroutinefunction(func):

        async def async_wrapper() -> Any:
            try:
                was_cached, result = await _get_cached_value(
                    func,
                    args,
                    kwargs,
                    ttl,
                    key_builder,
                    key_prefix,
                    exclude_args,
                )
                return result
            except Exception as e:
                # If caching fails, still try to execute the function
                logger.error(
                    f"Cache operation failed for async function {func.__name__}: {e}"
                )
                func_name = f"{getattr(func, '__module__', 'unknown')}.{getattr(func, '__qualname__', func.__name__)}"

                # Emit function error event
                try:
                    await events.emit(
                        EventType.FUNCTION_ERROR,
                        {
                            "function": func_name,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "phase": "cache_operation",
                        },
                    )
                except Exception:
                    pass  # Don't let event emission errors break function execution

                # Fall back to direct function execution
                try:
                    return await func(*args, **kwargs)
                except Exception as func_error:
                    logger.error(f"Function execution also failed: {func_error}")
                    raise func_error from e

        return async_wrapper()

    # For sync functions, we need to run the cache operations in an event loop
    def sync_wrapper() -> Any:
        try:
            # Try to get the current event loop
            try:
                loop = asyncio.get_running_loop()
                # We're already in an event loop, need to handle this carefully
                logger.debug("Already in event loop, creating task for cache operation")

                # Create a task for the cache operation
                task = asyncio.create_task(
                    _get_cached_value(
                        func,
                        args,
                        kwargs,
                        ttl,
                        key_builder,
                        key_prefix,
                        exclude_args,
                    )
                )

                # This is a sync function, but we're in an async context
                # We need to return a coroutine that can be awaited
                async def await_result():
                    was_cached, result = await task
                    return result

                return await_result()

            except RuntimeError:
                # No running event loop, we can create one
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # This shouldn't happen after the above check, but just in case
                        logger.warning(
                            "Event loop is running but get_running_loop() failed"
                        )
                        # Fall back to direct function execution
                        return func(*args, **kwargs)
                except RuntimeError:
                    # No event loop exists, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # Run the async cache operation
                try:
                    was_cached, result = loop.run_until_complete(
                        _get_cached_value(
                            func,
                            args,
                            kwargs,
                            ttl,
                            key_builder,
                            key_prefix,
                            exclude_args,
                        )
                    )
                    return result
                finally:
                    # Clean up the loop if we created it
                    if not loop.is_running():
                        try:
                            loop.close()
                        except Exception:
                            pass

        except Exception as e:
            # If caching fails, fall back to direct function execution
            logger.error(
                f"Cache operation failed for sync function {func.__name__}: {e}"
            )
            return func(*args, **kwargs)

    return sync_wrapper()
