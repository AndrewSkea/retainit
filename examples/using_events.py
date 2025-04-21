"""Example of using the retainit events system.

This example demonstrates how to subscribe to and handle events emitted by retainit.
It shows different ways to subscribe to events and how to use them for various purposes.
"""

import asyncio
import time
from datetime import datetime

import retainit
from retainit import EventType, events, on, retain


# 1. Simple function using the decorator pattern
@on(EventType.CACHE_HIT)
def log_cache_hit(event_data):
    """Log when there's a cache hit."""
    print(f"CACHE HIT: Function {event_data['function']} at {datetime.now()}")


@on(EventType.CACHE_MISS)
def log_cache_miss(event_data):
    """Log when there's a cache miss."""
    print(f"CACHE MISS: Function {event_data['function']} at {datetime.now()}")


# 2. Simple async handler
@on(EventType.FUNCTION_CALL_END)
async def log_function_duration(event_data):
    """Log the duration of function calls."""
    duration = event_data.get('duration', 0)
    print(f"FUNCTION CALL: {event_data['function']} took {duration:.4f} seconds")


# 3. Create a cache hit/miss counter
cache_stats = {
    "hits": 0,
    "misses": 0,
    "total": 0,
}

def update_hit_counter(event_data):
    """Update the hit counter when there's a cache hit."""
    cache_stats["hits"] += 1
    cache_stats["total"] += 1

def update_miss_counter(event_data):
    """Update the miss counter when there's a cache miss."""
    cache_stats["misses"] += 1
    cache_stats["total"] += 1

# Subscribe the counter functions
events.subscribe(EventType.CACHE_HIT, update_hit_counter)
events.subscribe(EventType.CACHE_MISS, update_miss_counter)


# 4. Create a comprehensive monitoring system
class CacheMonitor:
    """Monitor cache performance and collect statistics."""
    
    def __init__(self):
        self.function_stats = {}
        
    def start(self):
        """Start monitoring by subscribing to events."""
        events.subscribe(EventType.CACHE_HIT, self.on_cache_hit)
        events.subscribe(EventType.CACHE_MISS, self.on_cache_miss)
        events.subscribe(EventType.FUNCTION_CALL_END, self.on_function_call)
        events.subscribe(EventType.FUNCTION_ERROR, self.on_function_error)
        
    def stop(self):
        """Stop monitoring by unsubscribing from events."""
        events.unsubscribe(EventType.CACHE_HIT, self.on_cache_hit)
        events.unsubscribe(EventType.CACHE_MISS, self.on_cache_miss)
        events.unsubscribe(EventType.FUNCTION_CALL_END, self.on_function_call)
        events.unsubscribe(EventType.FUNCTION_ERROR, self.on_function_error)
    
    def on_cache_hit(self, event_data):
        """Handle cache hit events."""
        func_name = event_data['function']
        if func_name not in self.function_stats:
            self._init_stats(func_name)
        
        self.function_stats[func_name]['hits'] += 1
    
    def on_cache_miss(self, event_data):
        """Handle cache miss events."""
        func_name = event_data['function']
        if func_name not in self.function_stats:
            self._init_stats(func_name)
        
        self.function_stats[func_name]['misses'] += 1
    
    def on_function_call(self, event_data):
        """Handle function call events."""
        func_name = event_data['function']
        if func_name not in self.function_stats:
            self._init_stats(func_name)
        
        duration = event_data.get('duration', 0)
        stats = self.function_stats[func_name]
        stats['calls'] += 1
        stats['total_duration'] += duration
        
        # Update min/max duration
        if duration < stats['min_duration'] or stats['min_duration'] == 0:
            stats['min_duration'] = duration
        if duration > stats['max_duration']:
            stats['max_duration'] = duration
    
    def on_function_error(self, event_data):
        """Handle function error events."""
        func_name = event_data['function']
        if func_name not in self.function_stats:
            self._init_stats(func_name)
        
        self.function_stats[func_name]['errors'] += 1
    
    def _init_stats(self, func_name):
        """Initialize statistics for a function."""
        self.function_stats[func_name] = {
            'hits': 0,
            'misses': 0,
            'calls': 0,
            'errors': 0,
            'total_duration': 0,
            'min_duration': 0,
            'max_duration': 0,
        }
    
    def get_report(self):
        """Generate a report of cache performance."""
        report = []
        
        # Overall statistics
        total_hits = sum(stats['hits'] for stats in self.function_stats.values())
        total_misses = sum(stats['misses'] for stats in self.function_stats.values())
        total_calls = sum(stats['calls'] for stats in self.function_stats.values())
        total_errors = sum(stats['errors'] for stats in self.function_stats.values())
        
        if total_hits + total_misses > 0:
            hit_rate = total_hits / (total_hits + total_misses) * 100
        else:
            hit_rate = 0
        
        report.append("=== Cache Performance Report ===")
        report.append(f"Total Cache Hits: {total_hits}")
        report.append(f"Total Cache Misses: {total_misses}")
        report.append(f"Total Function Calls: {total_calls}")
        report.append(f"Total Errors: {total_errors}")
        report.append(f"Overall Hit Rate: {hit_rate:.2f}%")
        report.append("")
        
        # Per-function statistics
        report.append("=== Per-Function Statistics ===")
        for func_name, stats in self.function_stats.items():
            if stats['hits'] + stats['misses'] > 0:
                func_hit_rate = stats['hits'] / (stats['hits'] + stats['misses']) * 100
            else:
                func_hit_rate = 0
            
            avg_duration = stats['total_duration'] / stats['calls'] if stats['calls'] > 0 else 0
            
            report.append(f"Function: {func_name}")
            report.append(f"  Hits: {stats['hits']}")
            report.append(f"  Misses: {stats['misses']}")
            report.append(f"  Hit Rate: {func_hit_rate:.2f}%")
            report.append(f"  Calls: {stats['calls']}")
            report.append(f"  Errors: {stats['errors']}")
            report.append(f"  Avg Duration: {avg_duration:.4f}s")
            report.append(f"  Min Duration: {stats['min_duration']:.4f}s")
            report.append(f"  Max Duration: {stats['max_duration']:.4f}s")
            report.append("")
        
        return "\n".join(report)


# Create a test function
@retain(ttl=5)  # Short TTL for testing
def slow_calculation(n):
    """A slow calculation function for testing."""
    print(f"Performing slow calculation for n={n}...")
    time.sleep(0.5)  # Simulate slow operation
    return n * n


@retain(ttl=5)
async def async_calculation(n):
    """An async calculation function for testing."""
    print(f"Performing async calculation for n={n}...")
    await asyncio.sleep(0.5)  # Simulate slow async operation
    return n * n * n


# Main function to run the example
async def main():
    # Initialize retainit
    retainit.init_dev()
    
    # Create and start the cache monitor
    monitor = CacheMonitor()
    monitor.start()
    
    # Test the sync function
    print("\n=== Testing Sync Function ===")
    for i in range(3):
        for n in [5, 10, 5]:  # Repeat 5 to test cache hits
            result = slow_calculation(n)
            print(f"Result: {result}")
    
    # Test the async function
    print("\n=== Testing Async Function ===")
    for i in range(3):
        for n in [2, 3, 2]:  # Repeat 2 to test cache hits
            result = await async_calculation(n)
            print(f"Result: {result}")
    
    # Demonstrate cache expiration
    print("\n=== Testing Cache Expiration ===")
    result1 = slow_calculation(42)
    print(f"First call result: {result1}")
    print("Waiting for cache to expire (5 seconds)...")
    await asyncio.sleep(6)  # Wait for TTL to expire
    result2 = slow_calculation(42)
    print(f"After expiration result: {result2}")
    
    # Print cache statistics
    print("\n=== Simple Cache Stats ===")
    print(f"Hits: {cache_stats['hits']}")
    print(f"Misses: {cache_stats['misses']}")
    print(f"Total: {cache_stats['total']}")
    print(f"Hit Rate: {cache_stats['hits'] / cache_stats['total'] * 100:.2f}%")
    
    # Print detailed report
    print("\n" + monitor.get_report())
    
    # Stop the monitor
    monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())