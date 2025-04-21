"""Core functionality for retainit.

This module contains the main `retain` decorator and related functionality
for caching function results.
"""

import asyncio
import functools
import hashlib
import inspect
import logging
import pickle
import time
import traceback
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from .config import CacheBackendType, config
from .events import EventType, events
from .settings import SerializerType, settings

# Setup logging
logger = logging.getLogger("retainit.core")

# Type definitions
F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")
P = TypeVar("P")
CacheKeyType = str
CacheValueType = Any


class CacheManager:
    """Manages cache operations across different backends.
    
    This class provides a unified interface for cache operations
    across different backend implementations.
    
    Attributes:
        backend: The current cache backend instance.
        ttl: Default time-to-live for cached values in seconds.
    """
    
    def __init__(self):
        """Initialize the cache manager."""
        self._backend = None
        self._initialized = False
    
    async def get(self, key: CacheKeyType, function_name: str) -> Optional[Any]:
        """Get a value from the cache.
        
        Args:
            key: The cache key to retrieve.
            function_name: The name of the function being cached (for events).
            
        Returns:
            The cached value, or None if not found.
        """
        self._ensure_initialized()
        
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
                    }
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
                    }
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
                }
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
        """
        self._ensure_initialized()
        
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
                }
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
                }
            )
            logger.error(f"Cache set error for {key}: {str(e)}")
    
    async def delete(self, key: CacheKeyType) -> None:
        """Delete a value from the cache.
        
        Args:
            key: The cache key to delete.
        """
        self._ensure_initialized()
        
        try:
            await self._backend.delete(key)
            # Emit cache delete event
            await events.emit(
                EventType.CACHE_DELETE,
                {
                    "key": key,
                    "backend": settings.backend.value,
                }
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
                }
            )
            logger.error(f"Cache delete error for {key}: {str(e)}")
    
    async def clear(self) -> None:
        """Clear all values from the cache."""
        self._ensure_initialized()
        
        try:
            await self._backend.clear()
            # Emit cache clear event
            await events.emit(
                EventType.CACHE_CLEAR,
                {
                    "backend": settings.backend.value,
                }
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
                }
            )
            logger.error(f"Cache clear error: {str(e)}")
    
    def _ensure_initialized(self) -> None:
        """Ensure the cache manager is initialized.
        
        This lazily initializes the backend when it is first used.
        
        Raises:
            RuntimeError: If the backend cannot be initialized.
        """
        if not self._initialized:
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
                    raise RuntimeError("Redis settings not configured")
                try:
                    from .backends.redis import RedisCache
                    self._backend = RedisCache(
                        url=settings.redis.url,
                        password=settings.redis.password,
                        ssl=settings.redis.ssl,
                        cert_reqs=settings.redis.cert_reqs,
                        ca_certs=settings.redis.ca_certs,
                        ttl=settings.ttl,
                    )
                except ImportError:
                    raise RuntimeError(
                        "Redis backend requires 'redis' package. "
                        "Install with 'pip install retainit[redis]'"
                    )
            elif backend_type == CacheBackendType.S3:
                if not settings.s3:
                    raise RuntimeError("S3 settings not configured")
                try:
                    from .backends.s3 import S3Cache
                    self._backend = S3Cache(
                        bucket=settings.s3.bucket,
                        prefix=settings.s3.prefix,
                        region=settings.s3.region,
                    )
                except ImportError:
                    raise RuntimeError(
                        "S3 backend requires 'aioboto3' package. "
                        "Install with 'pip install retainit[aws]'"
                    )
            elif backend_type == CacheBackendType.DYNAMODB:
                if not settings.dynamodb:
                    raise RuntimeError("DynamoDB settings not configured")
                try:
                    from .backends.dynamodb import DynamoDBCache
                    self._backend = DynamoDBCache(
                        table=settings.dynamodb.table,
                        region=settings.dynamodb.region,
                    )
                except ImportError:
                    raise RuntimeError(
                        "DynamoDB backend requires 'aioboto3' package. "
                        "Install with 'pip install retainit[aws]'"
                    )
            else:
                raise RuntimeError(f"Unsupported backend: {backend_type}")
            
            # Emit backend initialization event
            asyncio.create_task(
                events.emit(
                    EventType.BACKEND_INIT,
                    {
                        "backend": backend_type.value,
                        "settings": {
                            "ttl": settings.ttl,
                            "compression": settings.compression,
                            "max_size": settings.max_size,
                        },
                    }
                )
            )
            
            self._initialized = True
            logger.debug(f"Cache manager initialized with backend: {backend_type}")


# Create a singleton instance
cache_manager = CacheManager()


def build_cache_key(
    func: Callable,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    key_builder: Optional[Callable] = None,
    key_prefix: Optional[str] = None,
    exclude_args: Optional[List[str]] = None,
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
    """
    if key_builder:
        return key_builder(func, *args, **kwargs)
    
    # Default key builder uses function name and arguments
    module_name = func.__module__
    func_name = func.__qualname__
    
    # Get argument names if we need to exclude some
    arg_names = []
    exclude_set = set(exclude_args or [])
    if exclude_set:
        sig = inspect.signature(func)
        arg_names = list(sig.parameters.keys())
    
    # Add args and kwargs to key
    arg_parts = []
    
    # Process positional arguments
    for i, arg in enumerate(args):
        # Skip excluded arguments
        if exclude_set and i < len(arg_names) and arg_names[i] in exclude_set:
            continue
        
        try:
            # Try to use a stable hash for the arg
            arg_parts.append(str(hash(arg)))
        except TypeError:
            # If not hashable, use its string representation
            arg_parts.append(str(arg))
    
    # Process keyword arguments
    for k, v in sorted(kwargs.items()):
        # Skip excluded arguments
        if k in exclude_set:
            continue
        
        try:
            arg_parts.append(f"{k}:{hash(v)}")
        except TypeError:
            arg_parts.append(f"{k}:{v}")
    
    # Create a deterministic key string
    key_str = f"{module_name}.{func_name}:{':'.join(arg_parts)}"
    
    # Hash for consistent length and to avoid problematic characters
    key_hash = hashlib.md5(key_str.encode()).hexdigest()
    
    # Use specified prefix or default
    prefix = key_prefix or settings.key_prefix
    return f"{prefix}:{key_hash}"


# Type overloads for better IDE type hints
@overload
def retain(func: F) -> F:
    ...


@overload
def retain(
    *,
    ttl: Optional[int] = None,
    key_builder: Optional[Callable] = None,
    key_prefix: Optional[str] = None,
    backend: Optional[CacheBackendType] = None,
    compression: Optional[bool] = None,
    serializer: Optional[SerializerType] = None,
    exclude_args: Optional[List[str]] = None,
) -> Callable[[F], F]:
    ...


def retain(
    func: Optional[F] = None,
    *,
    ttl: Optional[int] = None,
    key_builder: Optional[Callable] = None,
    key_prefix: Optional[str] = None,
    backend: Optional[CacheBackendType] = None,
    compression: Optional[bool] = None,
    serializer: Optional[SerializerType] = None,
    exclude_args: Optional[List[str]] = None,
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
        The decorated function.
        
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
    # If called without arguments, just decorate the function
    if func is not None:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return _wrapped_func(func, args, kwargs)
        
        # Add utilities to the wrapped function
        wrapper.cache_clear = cache_manager.clear
        wrapper.cache_delete = lambda *a, **kw: cache_manager.delete(
            build_cache_key(func, a, kw, key_builder, key_prefix, exclude_args)
        )
        
        return cast(F, wrapper)
    
    # If called with arguments, return a decorator
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return _wrapped_func(
                func, args, kwargs, ttl, key_builder, key_prefix,
                backend, compression, serializer, exclude_args
            )
        
        # Add utilities to the wrapped function
        wrapper.cache_clear = cache_manager.clear
        wrapper.cache_delete = lambda *a, **kw: cache_manager.delete(
            build_cache_key(func, a, kw, key_builder, key_prefix, exclude_args)
        )
        
        return cast(F, wrapper)
    
    return decorator


async def _get_cached_value(
    func: Callable,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    ttl: Optional[int] = None,
    key_builder: Optional[Callable] = None,
    key_prefix: Optional[str] = None,
    exclude_args: Optional[List[str]] = None,
) -> Tuple[bool, Any]:
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
    """
    # Generate cache key
    key = build_cache_key(func, args, kwargs, key_builder, key_prefix, exclude_args)
    func_name = f"{func.__module__}.{func.__qualname__}"
    
    # Try to get from cache
    cached_value = await cache_manager.get(key, func_name)
    if cached_value is not None:
        return True, cached_value
    
    # Call the function
    try:
        # Emit function call start event
        await events.emit(
            EventType.FUNCTION_CALL_START,
            {
                "function": func_name,
                "key": key,
                "args_count": len(args),
                "kwargs_count": len(kwargs),
            }
        )
        
        start_time = time.time()
        
        # Call the function based on whether it's async or not
        if asyncio.iscoroutinefunction(func):
            result = await func(*args, **kwargs)
        else:
            result = func(*args, **kwargs)
        
        duration = time.time() - start_time
        
        # Emit function call end event
        await events.emit(
            EventType.FUNCTION_CALL_END,
            {
                "function": func_name,
                "key": key,
                "duration": duration,
                "result_type": type(result).__name__,
            }
        )
        
        # Cache the result
        await cache_manager.set(key, result, func_name, ttl)
        
        return False, result
    except Exception as e:
        # Emit function error event
        await events.emit(
            EventType.FUNCTION_ERROR,
            {
                "function": func_name,
                "key": key,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }
        )
        
        logger.error(f"Error in function {func_name}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise


def _wrapped_func(
    func: Callable,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    ttl: Optional[int] = None,
    key_builder: Optional[Callable] = None,
    key_prefix: Optional[str] = None,
    backend: Optional[CacheBackendType] = None,
    compression: Optional[bool] = None,
    serializer: Optional[SerializerType] = None,
    exclude_args: Optional[List[str]] = None,
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
    """
    # TODO: Handle backend, compression, and serializer overrides
    
    # If the function is async, return an async wrapper
    if asyncio.iscoroutinefunction(func):
        async def async_wrapper():
            was_cached, result = await _get_cached_value(
                func, args, kwargs, ttl, key_builder, key_prefix, exclude_args
            )
            return result
        
        return async_wrapper()
    
    # For sync functions, we need to run the cache operations in an event loop
    def sync_wrapper():
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an existing event loop, use nest_asyncio
            try:
                import nest_asyncio
                nest_asyncio.apply()
            except ImportError:
                logger.warning(
                    "Function called from running event loop but nest_asyncio not installed. "
                    "Install with 'pip install nest_asyncio' for better support."
                )
        
        # Create or get an event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the async function
        was_cached, result = loop.run_until_complete(
            _get_cached_value(func, args, kwargs, ttl, key_builder, key_prefix, exclude_args)
        )
        
        return result
    
    return sync_wrapper()