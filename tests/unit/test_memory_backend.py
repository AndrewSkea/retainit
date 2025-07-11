"""Tests for memory cache backend."""

import asyncio
import time
from unittest.mock import patch

import pytest

from retainit.backends.memory import MemoryCache
from retainit.exceptions import BackendError, ValidationError


class TestMemoryCache:
    """Test memory cache backend."""

    @pytest.fixture
    async def cache(self):
        """Create a memory cache for testing."""
        cache = MemoryCache(max_size=10)
        try:
            yield cache
        finally:
            await cache.clear()

    async def test_basic_operations(self, cache):
        """Test basic cache operations."""
        # Test set and get
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

        # Test get non-existent key
        result = await cache.get("nonexistent")
        assert result is None

    async def test_ttl_expiration(self, cache):
        """Test TTL expiration."""
        # Set with short TTL
        await cache.set("key1", "value1", ttl=1)

        # Should be available immediately
        result = await cache.get("key1")
        assert result == "value1"

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache.get("key1")
        assert result is None

    async def test_delete(self, cache):
        """Test delete operation."""
        await cache.set("key1", "value1")
        await cache.delete("key1")

        result = await cache.get("key1")
        assert result is None

    async def test_clear(self, cache):
        """Test clear operation."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        await cache.clear()

        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    async def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = MemoryCache(max_size=3)

        try:
            # Fill cache to capacity
            await cache.set("key1", "value1")
            await cache.set("key2", "value2")
            await cache.set("key3", "value3")

            # Access key1 to make it more recent
            await cache.get("key1")

            # Add another item, should evict key2 (least recently used)
            await cache.set("key4", "value4")

            assert await cache.get("key1") == "value1"  # Still there
            assert await cache.get("key2") is None  # Evicted
            assert await cache.get("key3") == "value3"  # Still there
            assert await cache.get("key4") == "value4"  # Newly added
        finally:
            await cache.clear()

    async def test_update_existing_key(self, cache):
        """Test updating existing key doesn't trigger eviction."""
        cache = MemoryCache(max_size=2)

        try:
            await cache.set("key1", "value1")
            await cache.set("key2", "value2")

            # Update existing key
            await cache.set("key1", "new_value1")

            # Should not have triggered eviction
            assert await cache.get("key1") == "new_value1"
            assert await cache.get("key2") == "value2"
        finally:
            await cache.clear()

    async def test_concurrent_access(self):
        """Test concurrent access to cache."""
        cache = MemoryCache(max_size=100)

        async def set_values(start, end):
            for i in range(start, end):
                await cache.set(f"key{i}", f"value{i}")

        async def get_values(start, end):
            results = []
            for i in range(start, end):
                result = await cache.get(f"key{i}")
                results.append(result)
            return results

        try:
            # Set values concurrently
            await asyncio.gather(
                set_values(0, 50),
                set_values(50, 100),
            )

            # Get values concurrently
            results1, results2 = await asyncio.gather(
                get_values(0, 50),
                get_values(50, 100),
            )

            # Verify all values are set correctly
            for i, result in enumerate(results1):
                assert result == f"value{i}"

            for i, result in enumerate(results2):
                assert result == f"value{i + 50}"
        finally:
            await cache.clear()

    async def test_get_stats(self, cache):
        """Test cache statistics."""
        # Initially empty
        stats = await cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["current_size"] == 0

        # Add some data and access it
        await cache.set("key1", "value1")
        await cache.get("key1")  # Hit
        await cache.get("key2")  # Miss

        stats = await cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["current_size"] == 1
        assert stats["hit_rate"] == 0.5

    async def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = MemoryCache()

        try:
            # Add some entries with different TTLs
            await cache.set("key1", "value1", ttl=1)
            await cache.set("key2", "value2", ttl=10)
            await cache.set("key3", "value3")  # No TTL

            # Wait for some to expire
            await asyncio.sleep(1.1)

            # Clean up expired entries
            cleaned = await cache.cleanup_expired()
            assert cleaned == 1  # key1 should be cleaned

            # Verify remaining entries
            assert await cache.get("key1") is None
            assert await cache.get("key2") == "value2"
            assert await cache.get("key3") == "value3"
        finally:
            await cache.clear()

    def test_invalid_max_size(self):
        """Test invalid max_size parameter."""
        with pytest.raises(ValidationError):
            MemoryCache(max_size=0)

        with pytest.raises(ValidationError):
            MemoryCache(max_size=-1)

    async def test_invalid_key_validation(self, cache):
        """Test validation of invalid keys."""
        with pytest.raises(ValidationError):
            await cache.get("")  # Empty key

        with pytest.raises(ValidationError):
            await cache.set("", "value")  # Empty key

    async def test_invalid_ttl_validation(self, cache):
        """Test validation of invalid TTL."""
        with pytest.raises(ValidationError):
            await cache.set("key", "value", ttl=0)  # Invalid TTL

    async def test_large_value_validation(self, cache):
        """Test validation of large values."""
        large_value = "x" * (2 * 1024 * 1024)  # 2MB

        with pytest.raises(ValidationError):
            await cache.set("key", large_value)

    async def test_error_handling(self, cache):
        """Test error handling in cache operations."""
        # Mock an internal error
        with patch.object(cache, "_evict_lru", side_effect=Exception("Mock error")):
            with pytest.raises(BackendError):
                # Fill cache to trigger eviction
                for i in range(20):
                    await cache.set(f"key{i}", f"value{i}")

    async def test_no_max_size_limit(self):
        """Test cache with no size limit."""
        cache = MemoryCache(max_size=None)

        try:
            # Add many items
            for i in range(1000):
                await cache.set(f"key{i}", f"value{i}")

            # All should be accessible
            for i in range(1000):
                result = await cache.get(f"key{i}")
                assert result == f"value{i}"
        finally:
            await cache.clear()

    async def test_access_time_updates(self, cache):
        """Test that access time is updated on get."""
        await cache.set("key1", "value1")

        # Get the initial access time
        initial_time = cache.cache["key1"][2]

        # Wait a bit and access again
        await asyncio.sleep(0.1)
        await cache.get("key1")

        # Access time should be updated
        new_time = cache.cache["key1"][2]
        assert new_time > initial_time

    async def test_empty_eviction(self):
        """Test eviction on empty cache."""
        cache = MemoryCache(max_size=1)

        # Should not raise error
        cache._evict_lru()

        await cache.clear()

    async def test_data_types(self, cache):
        """Test different data types in cache."""
        test_data = [
            ("string", "hello"),
            ("int", 42),
            ("float", 3.14),
            ("bool", True),
            ("list", [1, 2, 3]),
            ("dict", {"key": "value"}),
            ("none", None),
        ]

        # Set all data types
        for key, value in test_data:
            await cache.set(key, value)

        # Get and verify all data types
        for key, expected_value in test_data:
            result = await cache.get(key)
            assert result == expected_value
            assert type(result) == type(expected_value)
