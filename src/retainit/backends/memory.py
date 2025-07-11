"""Memory cache backend implementation.

This module provides an in-memory cache backend using a dictionary with LRU eviction policy.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple, TypeVar

from ..backends.base import CacheBackend
from ..exceptions import BackendError, ValidationError
from ..validation import validate_cache_key, validate_ttl, validate_value_size

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MemoryCache(CacheBackend[T]):
    """In-memory LRU cache implementation.

    This cache stores values in memory using a dictionary with LRU (Least Recently Used)
    eviction policy when the maximum size is reached.

    Attributes:
        max_size: Maximum number of items to store in the cache.
        cache: Dictionary mapping keys to (value, expiry, last_access) tuples.
        lock: Lock to ensure thread-safe operations.
    """

    def __init__(
        self, max_size: Optional[int] = None, max_value_size: int = 1024 * 1024
    ):
        """Initialize the memory cache.

        Args:
            max_size: Maximum number of items to store in the cache. If None, no limit is applied.
            max_value_size: Maximum size of individual values in bytes.

        Raises:
            ValidationError: If max_size is invalid.
        """
        if max_size is not None and max_size <= 0:
            raise ValidationError(
                f"max_size must be positive, got {max_size}",
                context={"max_size": max_size},
            )

        self.max_size = max_size
        self.max_value_size = max_value_size
        self.cache: Dict[str, Tuple[Any, Optional[float], float]] = (
            {}
        )  # key -> (value, expiry, last_access)
        self.lock = asyncio.Lock()
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "evictions": 0,
        }

    async def get(self, key: str) -> Optional[T]:
        """Get a value from the cache.

        Args:
            key: The key to retrieve.

        Returns:
            The cached value, or None if not found or expired.

        Raises:
            BackendError: If the operation fails.
        """
        validate_cache_key(key)

        try:
            async with self.lock:
                if key not in self.cache:
                    self.stats["misses"] += 1
                    logger.debug(f"Cache miss for key: {key}")
                    return None

                value, expiry, _ = self.cache[key]

                # Check if expired
                current_time = time.time()
                if expiry and current_time > expiry:
                    await self._delete_internal(key)
                    self.stats["misses"] += 1
                    logger.debug(f"Cache miss (expired) for key: {key}")
                    return None

                # Update last access time (for LRU)
                self.cache[key] = (value, expiry, current_time)
                self.stats["hits"] += 1
                logger.debug(f"Cache hit for key: {key}")
                return value

        except Exception as e:
            logger.error(f"Error getting value for key {key}: {e}")
            raise BackendError(
                f"Failed to get value from memory cache: {e}",
                context={"key": key, "error": str(e)},
            ) from e

    async def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """Set a value in the cache.

        Args:
            key: The key to set.
            value: The value to cache.
            ttl: Time to live in seconds. If None, the value will not expire.

        Raises:
            BackendError: If the operation fails.
            ValidationError: If the input is invalid.
        """
        validate_cache_key(key)
        if ttl is not None:
            validate_ttl(ttl)
        validate_value_size(value, self.max_value_size)

        try:
            async with self.lock:
                # Enforce max size by removing least recently used items
                if (
                    self.max_size
                    and len(self.cache) >= self.max_size
                    and key not in self.cache
                ):
                    self._evict_lru()

                expiry = time.time() + ttl if ttl else None
                self.cache[key] = (value, expiry, time.time())
                self.stats["sets"] += 1
                logger.debug(f"Set value for key: {key}")

        except (ValidationError, BackendError):
            raise
        except Exception as e:
            logger.error(f"Error setting value for key {key}: {e}")
            raise BackendError(
                f"Failed to set value in memory cache: {e}",
                context={"key": key, "error": str(e)},
            ) from e

    async def delete(self, key: str) -> None:
        """Delete a value from the cache.

        Args:
            key: The key to delete.

        Raises:
            BackendError: If the operation fails.
        """
        validate_cache_key(key)

        try:
            async with self.lock:
                await self._delete_internal(key)

        except Exception as e:
            logger.error(f"Error deleting key {key}: {e}")
            raise BackendError(
                f"Failed to delete value from memory cache: {e}",
                context={"key": key, "error": str(e)},
            ) from e

    async def _delete_internal(self, key: str) -> None:
        """Internal delete method (assumes lock is held)."""
        if key in self.cache:
            del self.cache[key]
            self.stats["deletes"] += 1
            logger.debug(f"Deleted key: {key}")

    async def clear(self) -> None:
        """Clear all values from the cache.

        Raises:
            BackendError: If the operation fails.
        """
        try:
            async with self.lock:
                count = len(self.cache)
                self.cache.clear()
                logger.info(f"Cleared {count} items from memory cache")

        except Exception as e:
            logger.error(f"Error clearing memory cache: {e}")
            raise BackendError(
                f"Failed to clear memory cache: {e}", context={"error": str(e)}
            ) from e

    def _evict_lru(self) -> None:
        """Evict the least recently used item from the cache."""
        if not self.cache:
            return

        # Find the key with the oldest last_access timestamp
        oldest_key = min(self.cache.items(), key=lambda x: x[1][2])[0]
        if oldest_key in self.cache:
            del self.cache[oldest_key]
            self.stats["evictions"] += 1
            logger.debug(f"Evicted LRU item with key: {oldest_key}")

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary containing cache statistics.
        """
        async with self.lock:
            return {
                **self.stats.copy(),
                "current_size": len(self.cache),
                "max_size": self.max_size,
                "hit_rate": (
                    self.stats["hits"] / (self.stats["hits"] + self.stats["misses"])
                    if (self.stats["hits"] + self.stats["misses"]) > 0
                    else 0.0
                ),
            }

    async def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns:
            Number of entries removed.
        """
        try:
            async with self.lock:
                current_time = time.time()
                expired_keys = [
                    key
                    for key, (_, expiry, _) in self.cache.items()
                    if expiry and current_time > expiry
                ]

                for key in expired_keys:
                    del self.cache[key]

                if expired_keys:
                    logger.debug(f"Cleaned up {len(expired_keys)} expired entries")

                return len(expired_keys)

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0
