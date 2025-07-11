"""Tests for the core retain decorator and cache manager."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from retainit.config import CacheBackendType
from retainit.core import CacheManager, build_cache_key, cache_manager, retain
from retainit.exceptions import CacheKeyError, ValidationError
from retainit.settings import settings


class TestCacheManager:
    """Test cases for the CacheManager class."""

    @pytest.fixture
    def fresh_cache_manager(self):
        """Create a fresh cache manager for testing."""
        manager = CacheManager()
        yield manager

    @pytest.mark.asyncio
    async def test_cache_manager_initialization(self, fresh_cache_manager):
        """Test that cache manager initializes correctly."""
        manager = fresh_cache_manager
        assert not manager._initialized
        assert manager._backend is None

    @pytest.mark.asyncio
    async def test_cache_manager_lazy_initialization(self, fresh_cache_manager):
        """Test that cache manager initializes backends lazily."""
        manager = fresh_cache_manager

        # Mock the settings to use memory backend
        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            await manager._ensure_initialized()

        assert manager._initialized
        assert manager._backend is not None

    @pytest.mark.asyncio
    async def test_cache_get_set_cycle(self, fresh_cache_manager):
        """Test basic get/set operations."""
        manager = fresh_cache_manager

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Test cache miss
            result = await manager.get("test_key", "test_function")
            assert result is None

            # Test cache set and hit
            await manager.set("test_key", "test_value", "test_function")
            result = await manager.get("test_key", "test_function")
            assert result == "test_value"

    @pytest.mark.asyncio
    async def test_cache_delete(self, fresh_cache_manager):
        """Test cache deletion."""
        manager = fresh_cache_manager

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Set a value
            await manager.set("test_key", "test_value", "test_function")

            # Verify it exists
            result = await manager.get("test_key", "test_function")
            assert result == "test_value"

            # Delete it
            await manager.delete("test_key")

            # Verify it's gone
            result = await manager.get("test_key", "test_function")
            assert result is None

    @pytest.mark.asyncio
    async def test_cache_clear(self, fresh_cache_manager):
        """Test cache clearing."""
        manager = fresh_cache_manager

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Set multiple values
            await manager.set("key1", "value1", "test_function")
            await manager.set("key2", "value2", "test_function")

            # Clear the cache
            await manager.clear()

            # Verify all values are gone
            result1 = await manager.get("key1", "test_function")
            result2 = await manager.get("key2", "test_function")
            assert result1 is None
            assert result2 is None


class TestCacheKeyBuilder:
    """Test cases for cache key building functionality."""

    def test_build_cache_key_basic(self):
        """Test basic cache key building."""

        def test_func(a, b):
            return a + b

        key = build_cache_key(test_func, (1, 2), {})
        assert isinstance(key, str)
        assert len(key) > 0
        assert key.startswith(settings.key_prefix)

    def test_build_cache_key_with_kwargs(self):
        """Test cache key building with keyword arguments."""

        def test_func(a, b=None):
            return a

        key1 = build_cache_key(test_func, (1,), {"b": 2})
        key2 = build_cache_key(test_func, (1,), {"b": 3})

        assert key1 != key2  # Different kwargs should produce different keys

    def test_build_cache_key_exclude_args(self):
        """Test cache key building with excluded arguments."""

        def test_func(a, b, c):
            return a + b + c

        key1 = build_cache_key(test_func, (1, 2, 3), {}, exclude_args=["b"])
        key2 = build_cache_key(test_func, (1, 999, 3), {}, exclude_args=["b"])

        assert key1 == key2  # Should be same since 'b' is excluded

    def test_build_cache_key_custom_builder(self):
        """Test cache key building with custom key builder."""

        def test_func(a, b):
            return a + b

        def custom_key_builder(func, *args, **kwargs):
            return f"custom_{args[0]}_{args[1]}"

        key = build_cache_key(test_func, (1, 2), {}, key_builder=custom_key_builder)
        assert key == "custom_1_2"

    def test_build_cache_key_custom_prefix(self):
        """Test cache key building with custom prefix."""

        def test_func(a):
            return a

        key = build_cache_key(test_func, (1,), {}, key_prefix="custom_prefix")
        assert key.startswith("custom_prefix:")

    def test_build_cache_key_invalid_custom_builder(self):
        """Test cache key building with invalid custom key builder."""

        def test_func(a):
            return a

        def bad_key_builder(func, *args, **kwargs):
            return 123  # Returns non-string

        with pytest.raises(CacheKeyError):
            build_cache_key(test_func, (1,), {}, key_builder=bad_key_builder)


class TestRetainDecorator:
    """Test cases for the retain decorator."""

    def test_retain_decorator_without_args(self):
        """Test retain decorator without arguments."""

        @retain
        def simple_func(x):
            return x * 2

        # Function should be wrapped
        assert hasattr(simple_func, "cache_clear")
        assert hasattr(simple_func, "cache_delete")
        assert hasattr(simple_func, "cache_info")

    def test_retain_decorator_with_args(self):
        """Test retain decorator with arguments."""

        @retain(ttl=60, key_prefix="test")
        def parameterized_func(x):
            return x * 3

        # Function should be wrapped with parameters
        assert hasattr(parameterized_func, "cache_clear")
        assert hasattr(parameterized_func, "cache_delete")
        assert hasattr(parameterized_func, "cache_info")

    def test_retain_decorator_validation(self):
        """Test retain decorator parameter validation."""
        with pytest.raises(ValidationError):

            @retain(ttl=-1)  # Invalid TTL
            def bad_func():
                pass

        with pytest.raises(ValidationError):

            @retain(exclude_args="not_a_list")  # Invalid exclude_args
            def bad_func2():
                pass

    def test_retain_decorator_on_non_callable(self):
        """Test retain decorator on non-callable objects."""
        with pytest.raises(ValidationError):
            retain("not_a_function")

    @pytest.mark.asyncio
    async def test_retain_async_function(self):
        """Test retain decorator on async functions."""
        call_count = 0

        @retain
        async def async_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # First call should execute the function
            result1 = await async_func(5)
            assert result1 == 10
            assert call_count == 1

            # Second call should use cache
            result2 = await async_func(5)
            assert result2 == 10
            assert call_count == 1  # Function not called again

    def test_retain_sync_function(self):
        """Test retain decorator on sync functions."""
        call_count = 0

        @retain
        def sync_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # First call should execute the function
            result1 = sync_func(5)
            assert result1 == 10
            assert call_count == 1

            # Second call should use cache
            result2 = sync_func(5)
            assert result2 == 10
            assert call_count == 1  # Function not called again

    @pytest.mark.asyncio
    async def test_retain_ttl_expiration(self):
        """Test TTL expiration in cached functions."""
        call_count = 0

        @retain(ttl=1)  # 1 second TTL
        async def func_with_ttl(x):
            nonlocal call_count
            call_count += 1
            return x

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # First call
            result1 = await func_with_ttl(1)
            assert result1 == 1
            assert call_count == 1

            # Second call immediately (should use cache)
            result2 = await func_with_ttl(1)
            assert result2 == 1
            assert call_count == 1

            # Wait for TTL to expire
            await asyncio.sleep(1.1)

            # Third call (should execute function again)
            result3 = await func_with_ttl(1)
            assert result3 == 1
            assert call_count == 2

    def test_retain_error_handling(self):
        """Test error handling in cached functions."""

        @retain
        def error_func():
            raise ValueError("Test error")

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Errors should propagate
            with pytest.raises(ValueError, match="Test error"):
                error_func()

    @pytest.mark.asyncio
    async def test_retain_cache_failure_graceful_degradation(self):
        """Test graceful degradation when cache operations fail."""
        call_count = 0

        @retain
        async def func_with_cache_failure(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Mock cache manager to raise exceptions
        with patch.object(cache_manager, "get", side_effect=Exception("Cache error")):
            with patch.object(
                cache_manager, "set", side_effect=Exception("Cache error")
            ):
                # Function should still work despite cache failures
                result = await func_with_cache_failure(5)
                assert result == 10
                assert call_count == 1

    def test_cache_info(self):
        """Test cache info functionality."""

        @retain
        def info_func():
            return "test"

        info = info_func.cache_info()
        assert isinstance(info, dict)
        assert "function_name" in info
        assert "backend_type" in info
        assert "cache_enabled" in info
        assert info["cache_enabled"] is True


class TestCacheManagerConcurrency:
    """Test cases for cache manager concurrency and thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_initialization(self):
        """Test that concurrent initialization is handled correctly."""
        manager = CacheManager()

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Start multiple initialization tasks concurrently
            tasks = [manager._ensure_initialized() for _ in range(10)]
            await asyncio.gather(*tasks)

            # Should only initialize once
            assert manager._initialized
            assert manager._backend is not None

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self):
        """Test concurrent cache operations."""
        manager = CacheManager()

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Perform concurrent cache operations
            async def cache_operation(i):
                await manager.set(f"key_{i}", f"value_{i}", "test_function")
                return await manager.get(f"key_{i}", "test_function")

            tasks = [cache_operation(i) for i in range(100)]
            results = await asyncio.gather(*tasks)

            # All operations should succeed
            for i, result in enumerate(results):
                assert result == f"value_{i}"
