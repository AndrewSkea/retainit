"""Base class for cache backends.

This module defines the interface that all cache backends must implement.
"""

import abc
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class CacheBackend(Generic[T], abc.ABC):
    """Abstract base class for all cache backends.

    This class defines the interface that all cache backends must implement.
    Cache backends are responsible for storing and retrieving values from a cache.
    """

    @abc.abstractmethod
    async def get(self, key: str) -> Optional[T]:
        """Get a value from the cache.

        Args:
            key: The key to retrieve.

        Returns:
            The cached value, or None if not found.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """Set a value in the cache.

        Args:
            key: The key to set.
            value: The value to cache.
            ttl: Time to live in seconds. If None, the value will not expire.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a value from the cache.

        Args:
            key: The key to delete.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def clear(self) -> None:
        """Clear all values from the cache."""
        raise NotImplementedError

    async def close(self) -> None:
        """Close any resources associated with the cache.

        This method should be called when the cache is no longer needed.
        The default implementation does nothing.
        """
        pass