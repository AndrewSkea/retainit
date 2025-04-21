"""Memory cache backend implementation.

This module provides an in-memory cache backend using a dictionary with LRU eviction policy.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple, TypeVar

from ..backends.base import CacheBackend

logger = logging.getLogger("retainit.backends.memory")

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

    def __init__(self, max_size: Optional[int] = None):
        """Initialize the memory cache.

        Args:
            max_size: Maximum number of items to store in the cache. If None, no limit is applied.
        """
        self.max_size = max_size
        self.cache: Dict[str, Tuple[Any, Optional[float], float]] = {}  # key -> (value, expiry, last_access)
        self.lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[T]:
        """Get a value from the cache.

        Args:
            key: The key to retrieve.

        Returns:
            The cached value, or None if not found or expired.
        """
        async with self.lock:
            if key not in self.cache:
                return None

            value, expiry, _ = self.cache[key]

            # Check if expired
            if expiry and time.time() > expiry:
                await self.delete(key)
                return None

            # Update last access time (for LRU)
            self.cache[key] = (value, expiry, time.time())
            return value

    async def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """Set a value in the cache.

        Args:
            key: The key to set.
            value: The value to cache.
            ttl: Time to live in seconds. If None, the value will not expire.
        """
        async with self.lock:
            # Enforce max size by removing least recently used items
            if self.max_size and len(self.cache) >= self.max_size and key not in self.cache:
                self._evict_lru()

            expiry = time.time() + ttl if ttl else None
            self.cache[key] = (value, expiry, time.time())

    async def delete(self, key: str) -> None:
        """Delete a value from the cache.

        Args:
            key: The key to delete.
        """
        async with self.lock:
            if key in self.cache:
                del self.cache[key]

    async def clear(self) -> None:
        """Clear all values from the cache."""
        async with self.lock:
            self.cache.clear()

    def _evict_lru(self) -> None:
        """Evict the least recently used item from the cache."""
        if not self.cache:
            return

        # Find the key with the oldest last_access timestamp
        oldest_key = min(self.cache.items(), key=lambda x: x[1][2])[0]
        if oldest_key in self.cache:
            del self.cache[oldest_key]
            logger.debug(f"Evicted LRU item with key: {oldest_key}")