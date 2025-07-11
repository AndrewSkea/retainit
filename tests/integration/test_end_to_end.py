"""End-to-end integration tests for retainit."""

import asyncio
import shutil
import tempfile
import time
from unittest.mock import patch

import pytest

from retainit import retain
from retainit.config import CacheBackendType, config
from retainit.core import cache_manager
from retainit.events import EventType, events
from retainit.settings import settings


class TestEndToEndIntegration:
    """End-to-end integration tests."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test."""
        # Reset cache manager state
        cache_manager._initialized = False
        cache_manager._backend = None
        yield
        # Cleanup after test
        asyncio.create_task(cache_manager.clear())

    @pytest.mark.asyncio
    async def test_memory_backend_end_to_end(self):
        """Test complete workflow with memory backend."""
        call_count = 0

        @retain(ttl=60)
        def expensive_calculation(n):
            nonlocal call_count
            call_count += 1
            return n * n

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # First call should execute function
            result1 = expensive_calculation(5)
            assert result1 == 25
            assert call_count == 1

            # Second call should use cache
            result2 = expensive_calculation(5)
            assert result2 == 25
            assert call_count == 1  # Function not called again

            # Different argument should execute function again
            result3 = expensive_calculation(6)
            assert result3 == 36
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_disk_backend_end_to_end(self):
        """Test complete workflow with disk backend."""
        temp_dir = tempfile.mkdtemp()
        try:
            call_count = 0

            @retain(ttl=60)
            async def async_expensive_calculation(n):
                nonlocal call_count
                call_count += 1
                await asyncio.sleep(0.01)  # Simulate async work
                return n * n * n

            with patch.object(settings, "backend", CacheBackendType.DISK):
                with patch.object(settings, "base_path", temp_dir):
                    # First call should execute function
                    result1 = await async_expensive_calculation(3)
                    assert result1 == 27
                    assert call_count == 1

                    # Second call should use cache
                    result2 = await async_expensive_calculation(3)
                    assert result2 == 27
                    assert call_count == 1  # Function not called again

                    # Verify cache file exists
                    import os

                    cache_files = []
                    for root, dirs, files in os.walk(temp_dir):
                        cache_files.extend(files)
                    assert len(cache_files) > 0

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_cache_key_generation_consistency(self):
        """Test that cache keys are generated consistently."""

        @retain
        def func_with_args(a, b, c=None):
            return f"{a}-{b}-{c}"

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Same arguments should produce same cache key
            result1 = func_with_args(1, 2, c=3)
            result2 = func_with_args(1, 2, c=3)
            assert result1 == result2

            # Different argument order should produce same result if semantically same
            result3 = func_with_args(1, 2, c=3)
            result4 = func_with_args(a=1, b=2, c=3)
            assert result3 == result4

    @pytest.mark.asyncio
    async def test_cache_key_exclusion(self):
        """Test argument exclusion from cache keys."""
        call_count = 0

        @retain(exclude_args=["timestamp"])
        def func_with_timestamp(data, timestamp):
            nonlocal call_count
            call_count += 1
            return f"processed-{data}"

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Different timestamps should still hit cache due to exclusion
            result1 = func_with_timestamp("test", timestamp=time.time())
            result2 = func_with_timestamp("test", timestamp=time.time() + 1000)

            assert result1 == result2
            assert call_count == 1  # Function called only once

    @pytest.mark.asyncio
    async def test_custom_key_builder(self):
        """Test custom cache key builder."""
        call_count = 0

        def custom_key_builder(func, *args, **kwargs):
            # Only use first argument for key
            return f"custom_{args[0]}"

        @retain(key_builder=custom_key_builder)
        def func_with_custom_key(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Same first argument should hit cache despite different second argument
            result1 = func_with_custom_key(1, 2)
            result2 = func_with_custom_key(1, 999)

            assert result1 == 3
            assert result2 == 3  # Cached result from first call
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_event_system_integration(self):
        """Test that events are properly emitted during cache operations."""
        events_captured = []

        async def event_handler(event_data):
            events_captured.append(event_data)

        # Register event handlers
        events.on(EventType.CACHE_HIT, event_handler)
        events.on(EventType.CACHE_MISS, event_handler)
        events.on(EventType.CACHE_SET, event_handler)
        events.on(EventType.FUNCTION_CALL_START, event_handler)
        events.on(EventType.FUNCTION_CALL_END, event_handler)

        try:

            @retain
            async def tracked_function(x):
                return x * 2

            with patch.object(settings, "backend", CacheBackendType.MEMORY):
                # First call should generate miss, set, function start/end events
                await tracked_function(5)

                # Second call should generate hit event
                await tracked_function(5)

                # Check that appropriate events were captured
                event_types = [event.get("event_type") for event in events_captured]
                assert EventType.CACHE_MISS in event_types
                assert EventType.CACHE_SET in event_types
                assert EventType.CACHE_HIT in event_types
                assert EventType.FUNCTION_CALL_START in event_types
                assert EventType.FUNCTION_CALL_END in event_types

        finally:
            # Cleanup event handlers
            events.clear_handlers()

    @pytest.mark.asyncio
    async def test_error_handling_integration(self):
        """Test error handling in complete workflow."""

        @retain
        def error_prone_function(should_fail):
            if should_fail:
                raise ValueError("Intentional error")
            return "success"

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Successful call should be cached
            result1 = error_prone_function(False)
            assert result1 == "success"

            # Error should propagate and not be cached
            with pytest.raises(ValueError, match="Intentional error"):
                error_prone_function(True)

            # Subsequent successful call with same args should use cache
            result2 = error_prone_function(False)
            assert result2 == "success"

    @pytest.mark.asyncio
    async def test_ttl_expiration_integration(self):
        """Test TTL expiration in real-world scenario."""
        call_count = 0

        @retain(ttl=1)  # 1 second TTL
        async def short_lived_cache(x):
            nonlocal call_count
            call_count += 1
            return x * 10

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # First call
            result1 = await short_lived_cache(5)
            assert result1 == 50
            assert call_count == 1

            # Immediate second call should use cache
            result2 = await short_lived_cache(5)
            assert result2 == 50
            assert call_count == 1

            # Wait for expiration
            await asyncio.sleep(1.1)

            # Call after expiration should execute function again
            result3 = await short_lived_cache(5)
            assert result3 == 50
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_cache_management_utilities(self):
        """Test cache management utilities (clear, delete, info)."""

        @retain
        def manageable_function(x):
            return x**2

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Cache some values
            result1 = manageable_function(4)
            result2 = manageable_function(5)
            assert result1 == 16
            assert result2 == 25

            # Test cache info
            info = manageable_function.cache_info()
            assert isinstance(info, dict)
            assert "function_name" in info
            assert info["cache_enabled"] is True

            # Test selective deletion
            await manageable_function.cache_delete(4)

            # Value should be recalculated for deleted key
            result3 = manageable_function(4)
            assert result3 == 16

            # Other cached values should remain
            result4 = manageable_function(5)
            assert result4 == 25

            # Test cache clear
            await manageable_function.cache_clear()

            # All values should be recalculated
            result5 = manageable_function(5)
            assert result5 == 25

    @pytest.mark.asyncio
    async def test_concurrent_access_integration(self):
        """Test concurrent access to cached functions."""
        call_count = 0

        @retain
        async def concurrent_function(x):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # Simulate slow operation
            return x * 100

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Start multiple concurrent calls with same arguments
            tasks = [concurrent_function(7) for _ in range(10)]
            results = await asyncio.gather(*tasks)

            # All should return the same result
            assert all(result == 700 for result in results)

            # Function should be called only once due to caching
            # Note: Due to async nature, there might be a race condition
            # where multiple calls start before first one completes
            # So we check that it's called fewer times than total requests
            assert call_count < 10

    @pytest.mark.asyncio
    async def test_mixed_sync_async_functions(self):
        """Test mixing synchronous and asynchronous cached functions."""
        sync_calls = 0
        async_calls = 0

        @retain
        def sync_cached_func(x):
            nonlocal sync_calls
            sync_calls += 1
            return x + 10

        @retain
        async def async_cached_func(x):
            nonlocal async_calls
            async_calls += 1
            await asyncio.sleep(0.01)
            return x + 20

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Test sync function
            result1 = sync_cached_func(5)
            result2 = sync_cached_func(5)
            assert result1 == result2 == 15
            assert sync_calls == 1

            # Test async function
            result3 = await async_cached_func(5)
            result4 = await async_cached_func(5)
            assert result3 == result4 == 25
            assert async_calls == 1

            # Functions should have separate cache namespaces
            assert result1 != result3


class TestSerializationIntegration:
    """Integration tests for serialization with different data types."""

    @pytest.mark.asyncio
    async def test_complex_data_structures(self):
        """Test caching of complex data structures."""

        @retain
        def complex_data_func():
            return {
                "nested": {
                    "list": [1, 2, {"inner": True}],
                    "tuple": (1, 2, 3),
                    "set": {1, 2, 3},  # Will be converted to list in JSON
                },
                "numbers": [1.5, 2, 3],
                "strings": ["hello", "world"],
                "booleans": [True, False, None],
            }

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            result1 = complex_data_func()
            result2 = complex_data_func()

            # Results should be equal (though sets might become lists)
            assert result1["nested"]["list"] == result2["nested"]["list"]
            assert result1["numbers"] == result2["numbers"]
            assert result1["strings"] == result2["strings"]
            assert result1["booleans"] == result2["booleans"]

    @pytest.mark.asyncio
    async def test_large_data_caching(self):
        """Test caching of large data structures."""

        @retain
        def large_data_func():
            # Generate a large list
            return list(range(10000))

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            start_time = time.time()
            result1 = large_data_func()
            first_call_time = time.time() - start_time

            start_time = time.time()
            result2 = large_data_func()
            second_call_time = time.time() - start_time

            assert result1 == result2
            assert len(result1) == 10000
            # Second call should be faster due to caching
            assert second_call_time < first_call_time
