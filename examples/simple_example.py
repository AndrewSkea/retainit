#!/usr/bin/env python3
"""Simple example demonstrating retainit basic functionality."""

import time
import asyncio
from retainit import retain

# Example 1: Basic function caching
@retain
def expensive_calculation(n):
    """A function that's expensive to run."""
    print(f"Computing factorial of {n}...")
    time.sleep(0.5)  # Simulate expensive work
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result

# Example 2: Async function caching
@retain
async def async_data_fetch(user_id):
    """Simulate an async API call."""
    print(f"Fetching data for user {user_id}...")
    await asyncio.sleep(0.3)  # Simulate network delay
    return {
        "user_id": user_id,
        "name": f"User {user_id}",
        "timestamp": time.time()
    }

# Example 3: TTL (Time To Live) caching
@retain(ttl=2)  # Cache for 2 seconds
def get_current_time():
    """Get current time with 2-second cache."""
    print("Getting current time...")
    return time.strftime("%H:%M:%S")

# Example 4: Custom key prefix
@retain(key_prefix="math", ttl=300)
def fibonacci(n):
    """Calculate fibonacci with custom key prefix."""
    print(f"Computing fibonacci({n})...")
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

async def main():
    print("=== Retainit Basic Example ===\n")
    
    # Test basic caching
    print("1. Basic Function Caching:")
    start = time.time()
    result1 = expensive_calculation(5)
    first_call_time = time.time() - start
    print(f"First call result: {result1} (took {first_call_time:.2f}s)")
    
    start = time.time()
    result2 = expensive_calculation(5)  # Should be cached
    second_call_time = time.time() - start
    print(f"Second call result: {result2} (took {second_call_time:.2f}s)")
    print(f"Speedup: {first_call_time / second_call_time:.1f}x faster!\n")
    
    # Test async caching
    print("2. Async Function Caching:")
    start = time.time()
    data1 = await async_data_fetch(123)
    first_async_time = time.time() - start
    print(f"First async call: {data1} (took {first_async_time:.2f}s)")
    
    start = time.time()
    data2 = await async_data_fetch(123)  # Should be cached
    second_async_time = time.time() - start
    print(f"Second async call: {data2} (took {second_async_time:.2f}s)")
    print(f"Async speedup: {first_async_time / second_async_time:.1f}x faster!\n")
    
    # Test TTL
    print("3. TTL (Time To Live) Caching:")
    time1 = get_current_time()
    print(f"Time 1: {time1}")
    
    await asyncio.sleep(1)  # Sleep 1 second
    time2 = get_current_time()  # Should use cache
    print(f"Time 2: {time2} (should be same, cached)")
    
    await asyncio.sleep(2)  # Sleep 2 more seconds (total 3, cache expired)
    time3 = get_current_time()  # Should fetch new time
    print(f"Time 3: {time3} (should be different, cache expired)\n")
    
    # Test fibonacci with caching
    print("4. Fibonacci with Caching:")
    start = time.time()
    fib_result = fibonacci(10)
    fib_time = time.time() - start
    print(f"fibonacci(10) = {fib_result} (took {fib_time:.3f}s)")
    
    # Cache info
    print("\n5. Cache Information:")
    info = expensive_calculation.cache_info()
    print(f"Cache info: {info}")

if __name__ == "__main__":
    asyncio.run(main())