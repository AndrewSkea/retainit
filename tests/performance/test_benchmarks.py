"""Performance benchmarks for retainit."""

import asyncio
import shutil
import tempfile
import time
from unittest.mock import patch

import pytest

from retainit import retain
from retainit.config import CacheBackendType
from retainit.core import cache_manager
from retainit.settings import settings


class TestCachingPerformance:
    """Performance benchmarks for caching operations."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test."""
        # Reset cache manager state
        cache_manager._initialized = False
        cache_manager._backend = None
        yield
        # Cleanup after test
        asyncio.create_task(cache_manager.clear())

    @pytest.mark.benchmark(group="cache_overhead")
    def test_memory_cache_overhead(self, benchmark):
        """Benchmark the overhead of memory caching."""

        @retain
        def simple_calculation(x):
            return x * 2

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Benchmark the cached function call
            result = benchmark(simple_calculation, 42)
            assert result == 84

    @pytest.mark.benchmark(group="cache_overhead")
    def test_disk_cache_overhead(self, benchmark):
        """Benchmark the overhead of disk caching."""
        temp_dir = tempfile.mkdtemp()
        try:

            @retain
            def simple_calculation(x):
                return x * 2

            with patch.object(settings, "backend", CacheBackendType.DISK):
                with patch.object(settings, "base_path", temp_dir):
                    # Benchmark the cached function call
                    result = benchmark(simple_calculation, 42)
                    assert result == 84
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.benchmark(group="cache_hits")
    def test_cache_hit_performance(self, benchmark):
        """Benchmark cache hit performance."""
        call_count = 0

        @retain
        def expensive_calculation(x):
            nonlocal call_count
            call_count += 1
            # Simulate expensive operation
            time.sleep(0.001)
            return x**2

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Prime the cache
            expensive_calculation(10)
            assert call_count == 1

            # Benchmark cache hit
            result = benchmark(expensive_calculation, 10)
            assert result == 100
            assert call_count == 1  # Function should not be called again

    @pytest.mark.benchmark(group="serialization")
    def test_large_object_serialization(self, benchmark):
        """Benchmark serialization of large objects."""

        @retain
        def large_object_func():
            return {
                "data": list(range(10000)),
                "metadata": {"created": time.time(), "version": 1},
                "nested": {f"key_{i}": f"value_{i}" for i in range(1000)},
            }

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            result = benchmark(large_object_func)
            assert len(result["data"]) == 10000
            assert len(result["nested"]) == 1000

    @pytest.mark.benchmark(group="concurrent_access")
    def test_concurrent_cache_access(self, benchmark):
        """Benchmark concurrent access to cached functions."""

        @retain
        async def async_calculation(x):
            await asyncio.sleep(0.001)  # Simulate async work
            return x * 3

        async def concurrent_calls():
            tasks = [async_calculation(i % 10) for i in range(100)]
            return await asyncio.gather(*tasks)

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            results = benchmark(asyncio.run, concurrent_calls())
            assert len(results) == 100
            # Check that we have correct results
            for i, result in enumerate(results):
                expected = (i % 10) * 3
                assert result == expected

    @pytest.mark.benchmark(group="key_generation")
    def test_cache_key_generation_performance(self, benchmark):
        """Benchmark cache key generation performance."""
        from retainit.core import build_cache_key

        def complex_function(a, b, c=None, d="default", **kwargs):
            return sum([a, b, c or 0]) + len(kwargs)

        args = (1, 2)
        kwargs = {"c": 3, "d": "test", "extra1": "value1", "extra2": "value2"}

        key = benchmark(build_cache_key, complex_function, args, kwargs)
        assert isinstance(key, str)
        assert len(key) > 0

    @pytest.mark.benchmark(group="different_backends")
    def test_memory_vs_disk_performance(self, benchmark):
        """Compare performance between memory and disk backends."""

        @retain
        def calculation(x):
            return sum(range(x))

        # Test with memory backend
        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            memory_result = benchmark.pedantic(
                calculation, args=(1000,), rounds=10, iterations=1
            )

        # Test with disk backend
        temp_dir = tempfile.mkdtemp()
        try:
            with patch.object(settings, "backend", CacheBackendType.DISK):
                with patch.object(settings, "base_path", temp_dir):
                    disk_result = benchmark.pedantic(
                        calculation, args=(1000,), rounds=10, iterations=1
                    )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        assert memory_result == disk_result == sum(range(1000))


class TestAsyncPerformance:
    """Performance benchmarks for async operations."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test."""
        cache_manager._initialized = False
        cache_manager._backend = None
        yield
        asyncio.create_task(cache_manager.clear())

    @pytest.mark.benchmark(group="async_overhead")
    def test_async_function_caching_overhead(self, benchmark):
        """Benchmark async function caching overhead."""

        @retain
        async def async_calculation(x):
            await asyncio.sleep(0.001)
            return x**0.5

        async def run_async_calc():
            return await async_calculation(64)

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            result = benchmark(asyncio.run, run_async_calc())
            assert abs(result - 8.0) < 0.001

    @pytest.mark.benchmark(group="async_concurrent")
    def test_async_concurrent_different_keys(self, benchmark):
        """Benchmark concurrent async calls with different cache keys."""

        @retain
        async def async_work(task_id):
            await asyncio.sleep(0.001)
            return task_id * 2

        async def concurrent_different_keys():
            tasks = [async_work(i) for i in range(50)]
            return await asyncio.gather(*tasks)

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            results = benchmark(asyncio.run, concurrent_different_keys())
            assert len(results) == 50
            for i, result in enumerate(results):
                assert result == i * 2

    @pytest.mark.benchmark(group="async_concurrent")
    def test_async_concurrent_same_keys(self, benchmark):
        """Benchmark concurrent async calls with same cache keys."""
        call_count = 0

        @retain
        async def async_expensive_work(value):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate expensive work
            return value**2

        async def concurrent_same_keys():
            # All tasks use the same key, should result in cache hits
            tasks = [async_expensive_work(5) for _ in range(20)]
            return await asyncio.gather(*tasks)

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            results = benchmark(asyncio.run, concurrent_same_keys())
            assert len(results) == 20
            assert all(result == 25 for result in results)
            # Due to async nature and race conditions, call_count might vary
            # but should be much less than 20 due to caching
            assert call_count < 20


class TestScalabilityBenchmarks:
    """Scalability benchmarks for different data sizes and cache sizes."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test."""
        cache_manager._initialized = False
        cache_manager._backend = None
        yield
        asyncio.create_task(cache_manager.clear())

    @pytest.mark.benchmark(group="scalability")
    def test_cache_size_scalability(self, benchmark):
        """Test performance with increasing cache sizes."""

        @retain
        def data_generator(size):
            return list(range(size))

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Test with increasingly large data sizes
            sizes = [100, 1000, 10000]

            def test_multiple_sizes():
                results = []
                for size in sizes:
                    result = data_generator(size)
                    results.append(len(result))
                return results

            results = benchmark(test_multiple_sizes)
            assert results == sizes

    @pytest.mark.benchmark(group="scalability")
    def test_many_cache_keys_performance(self, benchmark):
        """Test performance with many different cache keys."""

        @retain
        def keyed_calculation(key_id):
            return key_id**2

        with patch.object(settings, "backend", CacheBackendType.MEMORY):

            def test_many_keys():
                results = []
                # Generate many different cache keys
                for i in range(1000):
                    result = keyed_calculation(i)
                    results.append(result)
                return results

            results = benchmark(test_many_keys)
            assert len(results) == 1000
            for i, result in enumerate(results):
                assert result == i**2

    @pytest.mark.benchmark(group="memory_usage")
    def test_memory_cache_eviction_performance(self, benchmark):
        """Test performance when memory cache eviction occurs."""
        from retainit.backends.memory import MemoryCache

        @retain
        def cached_function(x):
            return x * 100

        # Use a small cache size to force evictions
        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            with patch.object(settings, "max_size", 10):  # Very small cache

                def test_with_evictions():
                    results = []
                    # Generate more items than cache can hold
                    for i in range(50):
                        result = cached_function(i)
                        results.append(result)
                    return results

                results = benchmark(test_with_evictions)
                assert len(results) == 50
                for i, result in enumerate(results):
                    assert result == i * 100


class TestRegressionBenchmarks:
    """Regression benchmarks to detect performance degradations."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test."""
        cache_manager._initialized = False
        cache_manager._backend = None
        yield
        asyncio.create_task(cache_manager.clear())

    @pytest.mark.benchmark(group="regression")
    def test_simple_cache_regression(self, benchmark):
        """Regression test for simple caching performance."""

        @retain
        def simple_add(a, b):
            return a + b

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # This should complete quickly and serve as a regression baseline
            result = benchmark(simple_add, 10, 20)
            assert result == 30

    @pytest.mark.benchmark(group="regression")
    def test_decorator_overhead_regression(self, benchmark):
        """Regression test for decorator overhead."""

        # Compare cached vs uncached function performance
        def uncached_function(x):
            return x * 2

        @retain
        def cached_function(x):
            return x * 2

        with patch.object(settings, "backend", CacheBackendType.MEMORY):
            # Prime the cache
            cached_function(100)

            # Benchmark cached function (should hit cache)
            cached_result = benchmark.pedantic(
                cached_function, args=(100,), rounds=5, iterations=10
            )
            assert cached_result == 200

    @pytest.mark.benchmark(group="regression")
    def test_key_generation_regression(self, benchmark):
        """Regression test for cache key generation performance."""
        from retainit.core import build_cache_key

        def test_function(a, b, c, d=None, **kwargs):
            return a + b + c

        args = (1, 2, 3)
        kwargs = {"d": 4, "e": 5, "f": 6}

        # This should complete quickly and serve as a regression baseline
        key = benchmark(build_cache_key, test_function, args, kwargs)
        assert isinstance(key, str)
        assert len(key) > 0
