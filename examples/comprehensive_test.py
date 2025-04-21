#!/usr/bin/env python
"""Comprehensive test script for retainit.

This script demonstrates all the key features of retainit in a single runnable example.
It tests multiple backends, event handling, and cache behavior.
"""

import asyncio
import logging
import os
import random
import time
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Import retainit
import retainit
from retainit import DiskConfig, EventType, MemoryConfig, RedisConfig, on, retain

# ---------- BACKEND CONFIGURATION ----------

print("\n===== CONFIGURING BACKENDS =====")

# Configure memory backend for volatile data
retainit.register_backend(
    "memory",
    MemoryConfig(
        max_size=100,
        ttl=10,  # 10 second TTL
        compression=False
    ),
    default=True  # Make this the default
)

print("Registered 'memory' backend (default)")

# Configure disk backend for persistent data
cache_dir = Path(".cache_test")
cache_dir.mkdir(exist_ok=True)

retainit.register_backend(
    "disk",
    DiskConfig(
        base_path=str(cache_dir),
        ttl=30,  # 30 second TTL
        compression=True
    )
)

print(f"Registered 'disk' backend (path: {cache_dir})")

# Configure Redis backend if available
try:
    import redis

    # Check if Redis server is running
    test_redis = redis.Redis(host="localhost", port=6379)
    test_redis.ping()  # This will raise an exception if Redis is not available
    
    retainit.register_backend(
        "redis",
        RedisConfig(
            url="redis://localhost:6379",
            ttl=60,  # 60 second TTL
        )
    )
    print("Registered 'redis' backend")
    REDIS_AVAILABLE = True
except (ImportError, redis.exceptions.ConnectionError):
    print("Redis not available, skipping Redis backend registration")
    REDIS_AVAILABLE = False

# List registered backends
backends = retainit.registry.list_backends()
print(f"Registered backends: {list(backends.keys())}")
print(f"Default backend: {retainit.registry.get_default_name()}")

# ---------- EVENT SETUP ----------

print("\n===== SETTING UP EVENT HANDLERS =====")

# 1. Simple event handlers using the decorator pattern
@on(EventType.CACHE_HIT)
def log_cache_hit(event_data):
    """Log when there's a cache hit."""
    print(f"EVENT: Cache hit for {event_data['function']} - key: {event_data['key']}")

@on(EventType.CACHE_MISS)
def log_cache_miss(event_data):
    """Log when there's a cache miss."""
    print(f"EVENT: Cache miss for {event_data['function']} - key: {event_data['key']}")

@on(EventType.FUNCTION_CALL_END)
def log_function_duration(event_data):
    """Log the duration of function calls."""
    duration = event_data.get('duration', 0)
    print(f"EVENT: Function {event_data['function']} took {duration:.4f} seconds")

print("Registered basic event handlers for cache hits, misses, and function durations")

# 2. Create a cache statistics tracker
class CacheStats:
    """Tracks cache statistics."""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.function_durations = {}
    
    def on_hit(self, event_data):
        self.hits += 1
    
    def on_miss(self, event_data):
        self.misses += 1
    
    def on_error(self, event_data):
        self.errors += 1
    
    def on_function_call(self, event_data):
        func = event_data['function']
        duration = event_data.get('duration', 0)
        
        if func not in self.function_durations:
            self.function_durations[func] = []
        
        self.function_durations[func].append(duration)
    
    def get_hit_rate(self):
        """Get the cache hit rate."""
        total = self.hits + self.misses
        if total == 0:
            return 0
        return self.hits / total * 100
    
    def get_summary(self):
        """Get a summary of cache statistics."""
        summary = []
        summary.append(f"Cache Hits: {self.hits}")
        summary.append(f"Cache Misses: {self.misses}")
        summary.append(f"Cache Errors: {self.errors}")
        summary.append(f"Cache Hit Rate: {self.get_hit_rate():.2f}%")
        
        if self.function_durations:
            summary.append("\nFunction Durations:")
            for func, durations in self.function_durations.items():
                avg_duration = sum(durations) / len(durations) if durations else 0
                func_name = func.split('.')[-1]  # Just the function name, not the full path
                summary.append(f"  {func_name}: {avg_duration:.4f}s avg ({len(durations)} calls)")
        
        return "\n".join(summary)

# Create and register the stats tracker
stats = CacheStats()
retainit.events.subscribe(EventType.CACHE_HIT, stats.on_hit)
retainit.events.subscribe(EventType.CACHE_MISS, stats.on_miss)
retainit.events.subscribe(EventType.CACHE_ERROR, stats.on_error)
retainit.events.subscribe(EventType.FUNCTION_CALL_END, stats.on_function_call)

print("Registered cache statistics tracker")

# ---------- TEST FUNCTIONS ----------

print("\n===== DEFINING TEST FUNCTIONS =====")

# 1. Basic function using default backend (memory)
@retain
def calculate_square(n):
    """Calculate the square of a number."""
    print(f"Calculating square of {n}...")
    time.sleep(0.1)  # Simulate computation
    return n * n

# 2. Function using disk backend
@retain(backend="disk")
def calculate_cube(n):
    """Calculate the cube of a number."""
    print(f"Calculating cube of {n}...")
    time.sleep(0.2)  # Simulate computation
    return n * n * n

# 3. Function using Redis backend if available
if REDIS_AVAILABLE:
    @retain(backend="redis")
    def calculate_factorial(n):
        """Calculate the factorial of a number."""
        print(f"Calculating factorial of {n}...")
        time.sleep(0.3)  # Simulate computation
        if n <= 1:
            return 1
        return n * calculate_factorial(n - 1)

# 4. Function with custom TTL
@retain(ttl=5)  # 5 second TTL
def get_timestamp():
    """Get the current timestamp."""
    print("Getting current timestamp...")
    time.sleep(0.1)  # Simulate computation
    return time.time()

# 5. Function with exclude_args
@retain(exclude_args=["api_key"])
def fetch_data(item_id, api_key):
    """Fetch data for an item."""
    print(f"Fetching data for item {item_id} with API key {api_key}...")
    time.sleep(0.2)  # Simulate API call
    return {"id": item_id, "name": f"Item {item_id}", "data": random.random()}

# 6. Async function
@retain
async def async_operation(n):
    """Perform an async operation."""
    print(f"Performing async operation for {n}...")
    await asyncio.sleep(0.2)  # Simulate async operation
    return n * 2

print("Defined test functions for each backend and feature")

# ---------- TESTING ----------

async def run_tests():
    """Run all tests."""
    print("\n===== RUNNING TESTS =====")
    
    # Test 1: Basic caching with memory backend
    print("\n----- Test 1: Basic Caching (Memory Backend) -----")
    print("First call (should miss):")
    result1 = calculate_square(5)
    print(f"Result: {result1}")
    
    print("\nSecond call (should hit):")
    result2 = calculate_square(5)
    print(f"Result: {result2}")
    
    # Test 2: Disk backend
    print("\n----- Test 2: Disk Backend -----")
    print("First call (should miss):")
    result1 = calculate_cube(4)
    print(f"Result: {result1}")
    
    print("\nSecond call (should hit):")
    result2 = calculate_cube(4)
    print(f"Result: {result2}")
    
    # Test 3: Redis backend (if available)
    if REDIS_AVAILABLE:
        print("\n----- Test 3: Redis Backend -----")
        print("First call (should miss for 3, but hit for 2 and 1):")
        result1 = calculate_factorial(3)
        print(f"Result: {result1}")
        
        print("\nSecond call (should hit for all):")
        result2 = calculate_factorial(3)
        print(f"Result: {result2}")
    
    # Test 4: TTL expiration
    print("\n----- Test 4: TTL Expiration -----")
    print("First call (should miss):")
    ts1 = get_timestamp()
    print(f"Timestamp: {ts1}")
    
    print("\nSecond call (should hit):")
    ts2 = get_timestamp()
    print(f"Timestamp: {ts2}")
    
    print("\nWaiting for TTL to expire (5 seconds)...")
    await asyncio.sleep(6)
    
    print("\nThird call after TTL expiration (should miss):")
    ts3 = get_timestamp()
    print(f"Timestamp: {ts3}")
    
    # Test 5: exclude_args
    print("\n----- Test 5: Excluding Arguments -----")
    print("First call with API key 'secret1' (should miss):")
    data1 = fetch_data(42, "secret1")
    print(f"Data: {data1}")
    
    print("\nSecond call with different API key 'secret2' (should hit because API key is excluded from cache key):")
    data2 = fetch_data(42, "secret2")
    print(f"Data: {data2}")
    
    # Test 6: Async function
    print("\n----- Test 6: Async Function -----")
    print("First async call (should miss):")
    async_result1 = await async_operation(7)
    print(f"Result: {async_result1}")
    
    print("\nSecond async call (should hit):")
    async_result2 = await async_operation(7)
    print(f"Result: {async_result2}")
    
    # Test 7: Cache management
    print("\n----- Test 7: Cache Management -----")
    print("Deleting cache entry for calculate_square(5)...")
    calculate_square.cache_delete(5)
    
    print("\nAfter deletion (should miss):")
    result3 = calculate_square(5)
    print(f"Result: {result3}")
    
    # Test cache clearing
    if REDIS_AVAILABLE:
        print("\nClearing the redis cache...")
        # Access internal details to clear specifically the Redis cache
        # This is not recommended for general use, but useful for testing
        from retainit.core import cache_manager
        await cache_manager.clear()
        
        print("\nAfter clearing (should miss):")
        result4 = calculate_factorial(3)
        print(f"Result: {result4}")
    
    # Print statistics
    print("\n===== CACHE STATISTICS =====")
    print(stats.get_summary())

# Run the tests
if __name__ == "__main__":
    asyncio.run(run_tests())
    
    # Clean up cache directory
    print("\nCleaning up test cache directory...")
    import shutil
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    
    print("\nTests completed!")