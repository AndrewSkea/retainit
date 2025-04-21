## Event System

retainit includes a flexible event system that allows users to hook into cache-related events and react to them. This event system replaces a dedicated metrics collector with a more general-purpose approach that can be used for metrics, logging, debugging, and more.

### Event Types

The event system defines a standard set of events:

```python
class EventType(str, Enum):
    """Types of events that can be emitted by retainit."""
    
    # Cache events
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    CACHE_SET = "cache_set"
    CACHE_DELETE = "cache_delete"
    CACHE_CLEAR = "cache_clear"
    CACHE_ERROR = "cache_error"
    
    # Function events
    FUNCTION_CALL_START = "function_call_start"
    FUNCTION_CALL_END = "function_call_end"
    FUNCTION_ERROR = "function_error"
    
    # Lifecycle events
    BACKEND_INIT = "backend_init"
    BACKEND_CLOSE = "backend_close"
```

### Subscribing to Events

There are multiple ways to subscribe to events:

#### Using the Decorator Pattern

```python
from retainit import retain, EventType, on

# Subscribe to cache hit events
@on(EventType.CACHE_HIT)
def log_cache_hit(event_data):
    print(f"Cache hit for {event_data['function']}")

# Subscribe to cache miss events
@on(EventType.CACHE_MISS)
def log_cache_miss(event_data):
    print(f"Cache miss for {event_data['function']}")

# Subscribe to function completion events
@on(EventType.FUNCTION_CALL_END)
def log_function_duration(event_data):
    duration = event_data.get('duration', 0)
    print(f"Function {event_data['function']} took {duration:.4f} seconds")
```

#### Using the Events API

```python
from retainit import events, EventType

# Subscribe directly
def track_errors(event_data):
    error = event_data.get('error')
    print(f"ERROR: {error} in {event_data.get('function', 'unknown')}")

# Register the handler
events.subscribe(EventType.FUNCTION_ERROR, track_errors)

# Later, unsubscribe if needed
events.unsubscribe(EventType.FUNCTION_ERROR, track_errors)

# Or unsubscribe all handlers for an event type
events.unsubscribe_all(EventType.CACHE_ERROR)
```

### Async Event Handlers

retainit supports both synchronous and asynchronous event handlers:

```python
from retainit import on, EventType

# Synchronous handler
@on(EventType.CACHE_HIT)
def sync_handler(event_data):
    print(f"Cache hit: {event_data['key']}")

# Asynchronous handler
@on(EventType.CACHE_MISS)
async def async_handler(event_data):
    # Can use await here
    await log_to_database(event_data)
```

### Helper Functions

retainit provides helper functions for common event use cases:

#### Prometheus Metrics

```python
from retainit import enable_prometheus_metrics
from prometheus_client import start_http_server

# Enable Prometheus metrics based on events
enable_prometheus_metrics()

# Start the Prometheus server
start_http_server(8000)
```

#### Logging

```python
from retainit import setup_logging_handlers
import logging

# Set up default logging handlers for events
setup_logging_handlers(level=logging.INFO)
```

### Custom Monitoring System

Users can build custom monitoring systems using the event system:

```python
from retainit import events, EventType

class CacheMonitor:
    """Monitor cache performance and collect statistics."""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.function_durations = {}
    
    def start(self):
        """Start monitoring."""
        events.subscribe(EventType.CACHE_HIT, self.on_hit)
        events.subscribe(EventType.CACHE_MISS, self.on_miss)
        events.subscribe(EventType.CACHE_ERROR, self.on_error)
        events.subscribe(EventType.FUNCTION_CALL_END, self.on_function_call)
    
    def stop(self):
        """Stop monitoring."""
        events.unsubscribe(EventType.CACHE_HIT, self.on_hit)
        events.unsubscribe(EventType.CACHE_MISS, self.on_miss)
        events.unsubscribe(EventType.CACHE_ERROR, self.on_error)
        events.unsubscribe(EventType.FUNCTION_CALL_END, self.on_function_call)
    
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
    
    def get_avg_duration(self, function=None):
        """Get the average function duration."""
        if function is not None:
            if function not in self.function_durations:
                return 0
            durations = self.function_durations[function]
        else:
            durations = [d for f_durations in self.function_durations.values() 
                         for d in f_durations]
        
        if not durations:
            return 0
        return sum(durations) / len(durations)
```

The event system provides a flexible foundation for building various monitoring, logging, and debugging tools without tying users to specific implementations.## Backend Registration System

retainit provides a flexible backend registration system that allows users to configure and use multiple cache backends simultaneously.

### Backend Configuration

Each backend type has its own strongly-typed configuration class:

```python
# Register multiple backends
from retainit import retain, RedisConfig, MemoryConfig, S3Config

# Redis backend for persistent data
retainit.register_backend(
    "persistent", 
    RedisConfig(
        url="redis://cache.example.com:6379",
        password="secret",
        ttl=3600,  # 1 hour
        ssl=True
    ),
    default=True  # Make this the default
)

# Memory backend for temporary data
retainit.register_backend(
    "temporary",
    MemoryConfig(
        max_size=10000,
        ttl=60  # 1 minute
    )
)

# S3 backend for large objects
retainit.register_backend(
    "blob_storage",
    S3Config(
        bucket="my-cache-bucket",
        prefix="cache",
        region="us-west-2"
    )
)

# Use specific backends
@retain(backend="persistent")
def get_user(user_id):
    # Uses the Redis backend
    return db.fetch_user(user_id)

@retain(backend="temporary")
def get_weather(city):
    # Uses the memory backend
    return api.fetch_weather(city)

@retain(backend="blob_storage")
def get_image(image_id):
    # Uses the S3 backend
    return storage.fetch_image(image_id)

# Uses the default backend (persistent in this case)
@retain
def get_product(product_id):
    return db.fetch_product(product_id)
```

### Configuration Classes

Each backend has its own configuration class with appropriate parameters:

```python
@dataclass
class BackendConfig:
    """Base class for all backend configurations."""
    ttl: Optional[int] = None
    compression: bool = False

@dataclass
class MemoryConfig(BackendConfig):
    """Configuration for in-memory cache backend."""
    max_size: Optional[int] = None

@dataclass
class DiskConfig(BackendConfig):
    """Configuration for disk-based cache backend."""
    base_path: str = ".cache/function_resp"

@dataclass
class RedisConfig(BackendConfig):
    """Configuration for Redis cache backend."""
    url: str = "redis://localhost:6379"
    password: Optional[str] = None
    ssl: bool = False
    cert_reqs: Optional[str] = None
    ca_certs: Optional[str] = None
    db: int = 0
    
@dataclass
class S3Config(BackendConfig):
    """Configuration for S3 cache backend."""
    bucket: str
    prefix: str = "retainit"
    region: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
```

This approach provides type safety, clear documentation of parameters, and flexibility for multiple backend configurations.## Testing Strategy

retainit follows a comprehensive testing strategy to ensure reliability, security, and performance across all environments and use cases.

### Unit Testing

The core testing approach focuses on 100% code coverage through unit tests:

1. **Component-Level Tests**: Each component is tested in isolation
   - Backend implementations
   - Serializers
   - Key generation
   - Configuration system

2. **Data Type Coverage**: Tests for all supported data types
   - Python primitives (str, int, dict, list, etc.)
   - NumPy arrays (all dtypes)
   - Pandas DataFrames (various schemas and index types)
   - Polars DataFrames
   - Arrow Tables
   - Custom objects
   - Nested structures

3. **Edge Cases**:
   - Empty values
   - Very large values
   - Special characters in keys
   - Unicode handling
   - NaN/Infinity values
   - Sparse data structures

4. **Error Cases**:
   - Network failures
   - Permission issues
   - Timeout conditions
   - Malformed inputs
   - Serialization errors

### Integration Testing

Tests that verify the interaction between components:

1. **Backend Integration**: Tests with actual backend services
   - Redis integration
   - S3 integration
   - DynamoDB integration
   - File system operations

2. **Framework Integration**: Tests with web frameworks
   - FastAPI integration
   - Django integration
   - Flask integration

3. **Cross-Component Testing**: Tests across component boundaries
   - Decorator → Key Generation → Backend → Serializer pipeline

### Performance Testing

Tests that verify the library meets performance expectations:

1. **Benchmark Suite**: Automated performance testing
   - Latency benchmarks
   - Throughput benchmarks
   - Memory usage

2. **Profile-Guided Optimization**: Tests to identify performance bottlenecks
   - Function call profiles
   - Memory profiles
   - Cache hit/miss analysis

3. **Comparison Benchmarks**: Compare against existing solutions
   - vs. functools.lru_cache
   - vs. cachetools
   - vs. django-cache-memoize
   - vs. aiocache

### Concurrency Testing

Tests focused on thread and process safety:

1. **Thread Safety Tests**: Verify thread-safe behavior
   - Concurrent read/write
   - Lock contention scenarios

2. **Process Safety Tests**: Verify process-safe behavior
   - Multi-process access to shared cache
   - File locking effectiveness

3. **Race Condition Tests**: Target potential race conditions
   - Expiry handling
   - Cache invalidation
   - Init/shutdown sequences

### Security Testing

Tests focused on security aspects:

1. **Penetration Tests**: Target security aspects
   - Injection attacks
   - Serialization vulnerabilities
   - Network security

2. **Fuzz Testing**: Random and malformed inputs
   - Key fuzzing
   - Value fuzzing
   - Configuration fuzzing

### System Testing

End-to-end tests of the whole system:

1. **Real-World Scenarios**: Tests based on real use cases
   - API caching
   - Database query caching
   - Expensive computation caching

2. **Long-Running Tests**: Tests over extended periods
   - Memory leak detection
   - Cache expiry behavior
   - Circuit breaker operation

### Test Infrastructure

The test infrastructure enables comprehensive testing:

1. **Mock Backends**: For testing without real infrastructure
   - MockRedis
   - Moto for AWS services
   - In-memory file system

2. **Containerized Testing**: Isolated environment testing
   - Docker containers for different backends
   - Docker Compose for multi-service testing

3. **CI/CD Integration**: Automated testing on commits
   - GitHub Actions integration
   - Test matrix for Python versions, OS, backends

### Test Coverage Goals

retainit aims for complete test coverage:

1. **Line Coverage**: 100% line coverage
2. **Branch Coverage**: 100% branch coverage 
3. **Mutation Testing**: Ensure tests are meaningful, not just covering lines

### Test Implementation

Tests are implemented using:

1. **pytest**: Main testing framework
2. **pytest-asyncio**: For testing async functions
3. **pytest-cov**: For coverage reporting
4. **pytest-benchmark**: For performance testing
5. **hypothesis**: For property-based testing

### Test Organization

Tests are organized by component and type:

```
tests/
├── unit/
│   ├── test_decorator.py
│   ├── test_key_generation.py
│   ├── test_serializers/
│   │   ├── test_pickle.py
│   │   ├── test_json.py
│   │   ├── test_pandas.py
│   │   └── ...
│   ├── test_backends/
│   │   ├── test_memory.py
│   │   ├── test_disk.py
│   │   ├── test_redis.py
│   │   └── ...
│   └── ...
├── integration/
│   ├── test_redis_integration.py
│   ├── test_s3_integration.py
│   ├── test_django_integration.py
│   └── ...
├── performance/
│   ├── test_latency.py
│   ├── test_throughput.py
│   └── ...
├── concurrency/
│   ├── test_thread_safety.py
│   ├── test_process_safety.py
│   └── ...
├── security/
│   ├── test_serialization_safety.py
│   ├── test_encryption.py
│   └── ...
└── system/
    ├── test_real_world_scenarios.py
    ├── test_long_running.py
    └── ...
```

### Testing in CI/CD

Automated testing is integrated into the CI/CD pipeline:

1. **Pull Request Workflow**:
   - Run unit tests
   - Run integration tests with mocks
   - Check coverage
   - Run linting and static analysis

2. **Nightly Workflow**:
   - Run full test suite including all backends
   - Run performance tests
   - Run long-running tests

3. **Release Workflow**:
   - Run full test suite
   - Generate coverage report
   - Publish test results## Security and Safety

Security and thread/process safety are critical for a production-ready caching library. retainit implements comprehensive measures to ensure both.

### Thread and Process Safety

#### Concurrency Protection

1. **Thread-Safe Operations**: All cache operations use appropriate locks to prevent race conditions:
   ```python
   # Internal implementation example
   async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
       async with self._lock:  # Thread-safety lock
           # Set operation
   ```

2. **Atomic Operations**: For backends that support it (Redis, DynamoDB), retainit uses atomic operations:
   ```python
   # Redis example
   await redis.set(key, value, nx=True, ex=ttl)  # Atomic set-if-not-exists with expiry
   ```

3. **Process-Safe File Locking**: For disk cache, file locking prevents multiple processes from writing simultaneously:
   ```python
   # File locking example
   with portalocker.Lock(path, 'wb', timeout=10) as f:
       f.write(serialized_data)
   ```

4. **Lock Timeouts**: All locks have appropriate timeouts to prevent deadlocks:
   ```python
   async with asyncio.timeout(5.0):
       async with self._lock:
           # Operation
   ```

#### Safe Serialization and Deserialization

1. **Pickle Security**: When using pickle, retainit implements safeguards:
   - Optional allowlist of safe classes
   - Configurable maximum object size
   - Timeout for deserialization

2. **Alternative Serializers**: Safer serialization options are available:
   ```python
   @retain(serializer="json")  # Use JSON instead of pickle
   def get_data():
       # ...
   ```

### Information Security

#### Data Protection

1. **Encryption At Rest**: Optional encryption for cached data:
   ```python
   @retain(encryption=True, encryption_key=KEY)  # Encrypt cached data
   def get_sensitive_data():
       # ...
   ```

2. **Sensitive Data Handling**:
   - Keys derived from function arguments can be hashed to prevent exposure
   - Option to exclude specific arguments from cache keys
   ```python
   @retain(exclude_args=["password", "token"])  # Don't include these in cache key
   def authenticate(username, password, token):
       # ...
   ```

3. **TTL Enforcement**: Strict TTL enforcement for all cached data

#### Network Security

1. **TLS for Remote Backends**: Enforced TLS for Redis, S3, and other remote backends:
   ```python
   retainit.init(
       backend="redis",
       redis_url="rediss://cache.example.com:6379",  # Note 'rediss' (TLS)
       redis_cert_reqs="CERT_REQUIRED",
       redis_ca_certs="/path/to/ca.pem"
   )
   ```

2. **Connection Pooling**: Secure connection pooling to prevent leaks

3. **Network Timeouts**: Configurable timeouts for all network operations

#### Access Control

1. **Backend Credentials**: Secure handling of backend credentials:
   - Support for credential providers (AWS IAM, Redis ACL)
   - Environment variable support to avoid hardcoded secrets
   - Integration with secret managers

2. **Minimal Permissions**: Documentation and helpers for setting up minimal-permission policies

#### Secure Defaults

1. **Secure by Default**: All security features are enabled by default
2. **No Remote Backends by Default**: Local backends only unless explicitly configured
3. **Development vs Production Modes**: Different security defaults for different environments

### Reliability and Resilience

#### Circuit Breakers

1. **Auto-Disable on Failure**: Automatic disabling of cache on repeated failures:
   ```python
   retainit.init(
       circuit_breaker=True,
       circuit_breaker_threshold=5,   # 5 failures
       circuit_breaker_timeout=60     # 60 seconds open
   )
   ```

2. **Per-Backend Circuit Breakers**: Isolate failures to specific backends

#### Fallback Strategies

1. **Multi-Level Caching**: Automatic fallback between cache levels:
   ```python
   retainit.init(
       backend="tiered",
       backends=["memory", "redis", "s3"],  # Try in order
   )
   ```

2. **Guaranteed Function Execution**: Always fall back to the original function:
   ```python
   # Internal implementation
   try:
       return await cache.get(key)
   except Exception as e:
       log_error(e)
       result = await original_function(*args, **kwargs)
       return result
   ```

#### Comprehensive Logging

1. **Detailed Error Logging**: Comprehensive logging of all errors
2. **Audit Logging**: Optional audit logs for sensitive operations
3. **Structured Logging**: JSON-formatted logs for better analysis

### Safe Operation in Distributed Systems

1. **Distributed Locks**: Support for distributed locks with Redis or other backends
2. **Cache Stampede Prevention**: Techniques to prevent cache stampede:
   - Probabilistic early expiration
   - Background refresh of nearly-expired items
   - Staggered TTLs

3. **Safe Cache Invalidation**: Patterns for safe invalidation in distributed systems:
   ```python
   # Tag-based invalidation
   retainit.invalidate_tag("user:profile", distributed=True)
   ```

### Monitoring and Alerting

1. **Health Checks**: Built-in health check endpoints
2. **Performance Metrics**: Detailed performance metrics
3. **Security Events**: Logging of security-relevant events

### Compliance Features

1. **Data Retention Controls**: Tools for enforcing data retention policies
2. **PII Handling**: Special handling for personally identifiable information
3. **Audit Trails**: Optional audit trails for all cache operations
# retainit: High-Performance Function Caching Library

> A lightweight, extensible Python caching system for expensive function calls with support for various backends and data types.

## Overview

FastCache is a Python library that provides a robust, production-ready solution for caching the results of function calls. It is designed to significantly improve application performance by caching the results of expensive operations such as API calls, database queries, and complex computations.

This document outlines the design and functionality of FastCache, serving as both a reference for contributors and a guide for users.

## Core Design Principles

1. **Performance-First**: Optimized for speed with Rust extensions for critical paths
2. **Flexibility**: Multiple storage backends with customizable behavior
3. **Reliability**: Robust error handling and fallback mechanisms
4. **Observability**: Comprehensive metrics and monitoring
5. **Developer Experience**: Simple, intuitive API with sensible defaults
6. **Framework Integration**: Seamless integration with popular Python frameworks
7. **Lightweight Core**: Minimal dependencies in the base package
8. **Modular Design**: Optional features available through extras

## Architecture

retainit consists of several components that work together to provide a seamless caching experience.

### Component Diagram

```
┌────────────────────┐      ┌─────────────────────┐
│   retain Decorator │──────▶   Cache Manager    │
└────────────────────┘      └──────────┬──────────┘
                                      │
                                      ▼
  ┌──────────────────────────────────────────────────────┐
  │                   Cache Backends                     │
  │                                                      │
  │ ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
  │ │ Memory  │  │  Disk   │  │  Redis  │  │   S3    │  │
  │ └─────────┘  └─────────┘  └─────────┘  └─────────┘  │
  └──────────────────────────────────────────────────────┘
           │                    │
           ▼                    ▼
  ┌─────────────────┐    ┌─────────────────┐
  │ Metrics System  │    │ Logging System  │
  └─────────────────┘    └─────────────────┘
```

### Core Components

1. **retain Decorator**: The user-facing API that wraps functions to cache their results
2. **Cache Manager**: Handles key generation, backend selection, and coordination
3. **Cache Backends**: Multiple storage implementations (Memory, Disk, Redis, S3)
4. **Metrics System**: Collects and reports performance and usage metrics
5. **Configuration System**: Manages settings from various sources

## Key Features

### Async Support

FastCache is fully compatible with asyncio, supporting both synchronous and asynchronous functions:

```python
# Caching a synchronous function
@fastcache.cached()
def get_user_data(user_id: int) -> dict:
    return db.fetch_user(user_id)

# Caching an asynchronous function
@fastcache.cached()
async def get_user_profile(user_id: int) -> dict:
    return await api.fetch_profile(user_id)
```

### Multiple Storage Backends

FastCache supports multiple storage backends to suit different use cases:

1. **Memory Cache**: Fast in-process caching with LRU eviction
2. **Disk Cache**: Persistent file-based caching with optional compression
3. **Redis Cache**: Distributed caching for multi-instance applications
4. **S3 Cache**: Cloud-based caching for serverless applications

### Robust Error Handling

FastCache includes comprehensive error handling:

1. **Auto Fallback**: If cache operations fail, the original function is called
2. **Error Logging**: Detailed logs of cache failures
3. **Metric Generation**: Cache errors tracked in metrics
4. **Circuit Breaking**: Optional automatic disabling of cache on repeated failures

### Comprehensive Metrics

FastCache provides detailed metrics for monitoring and optimization:

1. **Cache Hit/Miss Rates**: Track cache effectiveness
2. **Latency Metrics**: Measure function execution times
3. **Error Rates**: Monitor cache and function failures
4. **Size Metrics**: Track cache size and eviction rates

### Advanced Features

1. **Key Generation**: Customizable key generation based on function arguments
2. **TTL Management**: Flexible time-to-live settings per function
3. **Cache Invalidation**: Manual and automatic cache clearing
4. **Cache Warming**: Preload cache for critical functions
5. **Compression**: Optional data compression for reduced memory/storage usage

## Configuration System

retainit provides a flexible configuration system with multiple approaches to fit different use cases.

### Backend Configuration

The primary configuration mechanism is through the backend registration system:

```python
import retainit
from retainit import retain, RedisConfig, DiskConfig

# Register a Redis backend
retainit.register_backend(
    "main_cache",
    RedisConfig(
        url="redis://localhost:6379",
        password="secret",
        ttl=3600,
        ssl=True
    ),
    default=True  # Make this the default backend
)

# Register a disk backend
retainit.register_backend(
    "local_cache",
    DiskConfig(
        base_path="/tmp/cache",
        compression=True
    )
)
```

### Configuration Sources (In Order of Precedence)

1. **Decorator Arguments**: Function-specific settings
2. **Registered Backends**: Named backend configurations
3. **Configuration Files**: Project-specific settings in config files
4. **Environment Variables**: Deployment environment settings
5. **Default Values**: Sensible defaults

### Configuration Files

retainit supports multiple configuration file formats:

**YAML (retainit.yaml)**:

```yaml
retainit:
  backends:
    default:
      type: memory
      ttl: 3600
      max_size: 10000
    
    persistent:
      type: redis
      url: redis://localhost:6379
      password: null
      ttl: 86400  # 1 day
    
    large_objects:
      type: s3
      bucket: my-cache-bucket
      prefix: cache
      region: us-west-2
  
  # Logging configuration
  logging:
    level: INFO
  
  # Environment profiles
  profiles:
    development:
      default_backend: memory
    production:
      default_backend: persistent
```

**JSON (retainit.json)**:

```json
{
  "retainit": {
    "backends": {
      "default": {
        "type": "memory",
        "ttl": 3600
      },
      "persistent": {
        "type": "redis",
        "url": "redis://localhost:6379",
        "ttl": 86400
      }
    }
  }
}
```

**TOML (pyproject.toml)**:

```toml
[tool.retainit.backends.default]
type = "memory"
ttl = 3600

[tool.retainit.backends.persistent]
type = "redis"
url = "redis://localhost:6379"
ttl = 86400
```

### Environment Variables

```bash
# Backend configurations
RETAINIT_BACKENDS_DEFAULT_TYPE=memory
RETAINIT_BACKENDS_DEFAULT_TTL=3600

RETAINIT_BACKENDS_REDIS_TYPE=redis
RETAINIT_BACKENDS_REDIS_URL=redis://localhost:6379
RETAINIT_BACKENDS_REDIS_PASSWORD=secret

# Default backend
RETAINIT_DEFAULT_BACKEND=redis

# Logging configuration
RETAINIT_LOG_LEVEL=INFO
```

### Programmatic Configuration

#### Legacy Configuration Style (Simple)

```python
import retainit

# Initialize with simple configuration
retainit.init(
    backend="redis",
    redis_url="redis://localhost:6379",
    ttl=3600
)

# Shorthand for common scenarios
retainit.init_dev()  # Development settings
retainit.init_prod(redis_url="redis://cache.example.com:6379")  # Production settings
retainit.init_test()  # Testing settings
```

#### Enhanced Configuration Style (Typed)

```python
from retainit import RedisConfig, MemoryConfig

# Configure multiple backends
retainit.register_backend("default", MemoryConfig(max_size=10000))
retainit.register_backend("redis", RedisConfig(url="redis://localhost:6379"))

# Load from a configuration file
retainit.load_config("config/cache.yaml")

# Load from environment variables
retainit.load_from_env()
```

### Decorator Configuration

```python
# Use the default backend
@retain
def get_data(id):
    return api.fetch_data(id)

# Use a specific registered backend
@retain(backend="redis")
def get_user(user_id):
    return db.fetch_user(user_id)

# Override specific settings
@retain(
    ttl=60,                    # 60 secon

## Usage Examples

### Basic Usage

```python
import retainit
from retainit import retain

# Initialize with defaults
retainit.init()

# Cache a synchronous function
@retain
def get_user(user_id):
    print("Fetching user...")
    return {"id": user_id, "name": "John Doe"}

# First call (cache miss)
user = get_user(123)  # Prints "Fetching user..."

# Second call (cache hit)
user = get_user(123)  # No print, returns cached result
```

### Asynchronous Usage

```python
import retainit
from retainit import retain
import asyncio

@retain
async def fetch_data(item_id):
    print(f"Fetching item {item_id}...")
    await asyncio.sleep(1)  # Simulate API call
    return {"id": item_id, "name": f"Item {item_id}"}

async def main():
    # First call (cache miss)
    item = await fetch_data(42)  # Prints "Fetching item 42..."
    
    # Second call (cache hit)
    item = await fetch_data(42)  # No print, returns cached result

asyncio.run(main())
```

### Custom Key Generation

```python
@retain(
    key_builder=lambda func, user_id, **kwargs: f"user:{user_id}"
)
def get_user_profile(user_id, include_details=False):
    # The cache key will be based only on user_id, ignoring include_details
    return api.fetch_user(user_id, include_details=include_details)
```

### Manual Cache Management

```python
@retain
def get_data(id):
    return api.fetch_data(id)

# Clear the entire cache
get_data.cache_clear()

# Delete a specific cache entry
get_data.cache_delete(42)

# Prefetch/warm the cache
_ = get_data(1)
_ = get_data(2)
_ = get_data(3)
```

### Framework Integration

#### FastAPI

```python
from fastapi import FastAPI
from retainit.ext.fastapi import setup_retainit
from retainit import retain

app = FastAPI()

# Set up retainit with the FastAPI app
setup_retainit(app, backend="redis", redis_url="redis://localhost:6379")

@app.get("/users/{user_id}")
@retain(ttl=30)
async def get_user(user_id: int):
    # Implementation
    return {"id": user_id, "name": "Example User"}
```

#### Django

```python
# settings.py
INSTALLED_APPS = [
    # ...
    'retainit.ext.django',
]

RETAINIT = {
    'BACKEND': 'redis',
    'REDIS_URL': 'redis://localhost:6379',
    'ENABLE_METRICS': True,
}

# views.py
from django.http import JsonResponse
from retainit.ext.django import retain

@retain(ttl=60)
def get_user(request, user_id):
    # Implementation
    return JsonResponse({"id": user_id, "name": "Example User"})
```

#### Flask

```python
from flask import Flask, jsonify
from retainit.ext.flask import setup_retainit, retain

app = Flask(__name__)

# Set up retainit with the Flask app
setup_retainit(app, backend="redis", redis_url="redis://localhost:6379")

@app.route("/users/<int:user_id>")
@retain(ttl=30)
def get_user(user_id):
    # Implementation
    return jsonify({"id": user_id, "name": "Example User"})
```

## Context Managers for Temporary Configuration

```python
# Temporarily use a different backend
with retainit.config_context(backend="memory"):
    result = expensive_function()

# Temporarily disable caching
with retainit.disabled():
    result = always_fresh_function()
```

## Metrics Integration

### Prometheus

```python
import retainit
from prometheus_client import start_http_server

retainit.init(
    enable_metrics=True,
    metrics_backend="prometheus",
    metrics_namespace="myapp"
)

# Start the Prometheus HTTP server
start_http_server(8000)
```

### Datadog

```python
import retainit

retainit.init(
    enable_metrics=True,
    metrics_backend="datadog",
    metrics_namespace="myapp"
)
```

### CloudWatch

```python
import retainit

retainit.init(
    enable_metrics=True,
    metrics_backend="cloudwatch",
    metrics_namespace="myapp"
)
```

## CLI Commands

retainit includes a command-line interface for managing caches:

```bash
# Clear all caches
python -m retainit clear

# View cache statistics
python -m retainit stats

# Test cache performance
python -m retainit benchmark

# Generate configuration template
python -m retainit init-config
```

## Performance Optimization

### Rust Extensions

For performance-critical paths, FastCache uses Rust extensions built with PyO3:

1. **Key Generation**: Fast hashing and serialization
2. **Memory Cache**: High-performance in-memory storage
3. **Redis Protocol**: Efficient Redis communication

### Serialization Strategies

FastCache provides a flexible serialization system:

1. **Core Serializers** (available in base package):
   - **Pickle**: Default Python serialization
   - **JSON**: Human-readable text format
   - **String/Bytes**: Simple string and binary data

2. **Optional Serializers** (available with extras):
   - **Pandas**: Efficient DataFrame serialization (requires `fcache[pandas]`)
   - **NumPy**: Array serialization (requires `fcache[numpy]`)
   - **Polars**: DataFrame serialization (requires `fcache[polars]`)
   - **Arrow**: Apache Arrow serialization (requires `fcache[arrow]`)
   - **MessagePack**: Compact binary format (requires `fcache[msgpack]`)

3. **Auto-detection**: FastCache can automatically select the appropriate serializer based on the data type

4. **Custom Serializers**: Plugin your own serializers for specialized data types

## Advanced Topics

### Distributed Caching

For multi-instance applications, FastCache supports distributed caching:

```python
fastcache.init(
    backend="redis",
    redis_url="redis://cache.example.com:6379",
    redis_cluster=True  # Enable Redis cluster support
)
```

### Cache Invalidation Patterns

FastCache supports several cache invalidation patterns:

1. **TTL-based**: Automatic expiration after a time period
2. **Manual**: Explicit clearing of specific entries
3. **Pattern-based**: Clear all entries matching a pattern
4. **Tag-based**: Associate entries with tags for group invalidation

```python
# Tag-based invalidation
@fastcache.cached(tags=["user", "profile"])
def get_user_profile(user_id):
    return api.fetch_profile(user_id)

# Later, invalidate all "user" tagged items
fastcache.invalidate_tag("user")
```

### Hybrid Caching

Combine multiple cache backends for tiered caching:

```python
fastcache.init(
    backend="hybrid",
    primary="memory",
    secondary="redis",
    redis_url="redis://localhost:6379"
)
```

## Error Handling and Circuit Breaking

FastCache includes a circuit breaker pattern to prevent cascading failures:

```python
fastcache.init(
    # Circuit breaker settings
    circuit_breaker_enabled=True,
    circuit_breaker_threshold=5,  # 5 failures trips the breaker
    circuit_breaker_timeout=60    # 60 seconds in open state
)
```

## Security Considerations

1. **Data Encryption**: Option to encrypt cached data
2. **Credential Handling**: Secure management of backend credentials
3. **Cache Poisoning**: Protection against cache poisoning attacks

## Conclusion

FastCache is designed to be a comprehensive, high-performance caching solution for Python applications. It combines the ease of use of Python with the performance of Rust, making it suitable for applications of any scale.

## Dependencies and Installation

retainit follows a modular design with minimal core dependencies, allowing users to install only what they need.

### Core Installation

The base installation includes only the essential components with no external dependencies:

```bash
pip install retainit
```

This provides:
- Memory cache backend
- Disk cache backend
- Basic serialization (pickle)
- Core functionality

### Optional Dependencies

Additional features are available through extras:

```bash
# Redis support
pip install retainit[redis]

# AWS support (S3, DynamoDB)
pip install retainit[aws]

# All metrics backends
pip install retainit[metrics]

# Specific metrics backends
pip install retainit[prometheus]
pip install retainit[datadog]
pip install retainit[cloudwatch]

# Framework integrations
pip install retainit[django]
pip install retainit[fastapi]
pip install retainit[flask]

# Data format support
pip install retainit[pandas]
pip install retainit[numpy]
pip install retainit[polars]
pip install retainit[arrow]

# All data formats
pip install retainit[data]

# Complete installation with all features
pip install retainit[all]
```

### Installation Groups

Here's what each installation group includes:

```
retainit[redis]: redis-py-cluster
retainit[aws]: aioboto3, s3fs
retainit[prometheus]: prometheus-client
retainit[datadog]: datadog
retainit[cloudwatch]: boto3
retainit[metrics]: prometheus-client, datadog, boto3
retainit[django]: django
retainit[fastapi]: fastapi
retainit[flask]: flask
retainit[pandas]: pandas
retainit[numpy]: numpy
retainit[polars]: polars
retainit[arrow]: pyarrow
retainit[data]: pandas, numpy, polars, pyarrow
retainit[all]: all of the above
```

### Package Configuration

In the `pyproject.toml`:

```toml
[project]
# Basic project info
name = "retainit"
version = "0.1.0"
# ...

[project.optional-dependencies]
redis = ["redis>=4.0.0", "redis-py-cluster>=2.1.0"]
aws = ["aioboto3>=9.0.0", "s3fs>=2023.1.0"]
prometheus = ["prometheus-client>=0.14.0"]
datadog = ["datadog>=0.44.0"]
cloudwatch = ["boto3>=1.24.0"]
metrics = ["prometheus-client>=0.14.0", "datadog>=0.44.0", "boto3>=1.24.0"]
django = ["django>=3.2.0"]
fastapi = ["fastapi>=0.68.0"]
flask = ["flask>=2.0.0"]
pandas = ["pandas>=1.3.0"]
numpy = ["numpy>=1.20.0"]
polars = ["polars>=0.15.0"]
arrow = ["pyarrow>=7.0.0"]
data = ["pandas>=1.3.0", "numpy>=1.20.0", "polars>=0.15.0", "pyarrow>=7.0.0"]
all = [
    "redis>=4.0.0", "redis-py-cluster>=2.1.0",
    "aioboto3>=9.0.0", "s3fs>=2023.1.0",
    "prometheus-client>=0.14.0", "datadog>=0.44.0", "boto3>=1.24.0",
    "django>=3.2.0", "fastapi>=0.68.0", "flask>=2.0.0",
    "pandas>=1.3.0", "numpy>=1.20.0", "polars>=0.15.0", "pyarrow>=7.0.0"
]
```

## Data Type Serialization

FastCache includes a flexible serialization system to handle various data types efficiently.

### Built-in Serializers

The core package includes basic serializers:

1. **Pickle Serializer**: Default for general Python objects
2. **JSON Serializer**: For JSON-compatible data structures
3. **String Serializer**: For simple string values
4. **Bytes Serializer**: For binary data

### Optional Data Type Serializers

When the appropriate extras are installed, FastCache automatically registers specialized serializers:

```python
# Example: Pandas DataFrame serialization
@fastcache.cached(serializer="pandas")
def get_dataframe():
    return pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
```

Supported data types with specialized serializers:

| Data Type | Required Extra | Serialization Format | Notes |
|-----------|---------------|---------------------|-------|
| Pandas DataFrame | `pandas` | Parquet | Preserves dtypes, indexes |
| Numpy Array | `numpy` | Binary NPY | Preserves shape, dtypes |
| Polars DataFrame | `polars` | Parquet | Preserves schema |
| Arrow Table | `arrow` | IPC Format | Native Arrow serialization |
| CSV Data | `pandas` | Compressed text | Optional type preservation |

### Auto-detection of Data Types

FastCache automatically detects and uses the appropriate serializer:

```python
@fastcache.cached()
def get_data():
    # FastCache detects this is a pandas DataFrame
    # and uses the pandas serializer if available
    return pd.DataFrame({"a": [1, 2, 3]})
```

### Custom Serializers

Users can register their own serializers for specialized data types:

```python
from fcache.serializers import register_serializer

@register_serializer("my_model")
class MyModelSerializer:
    def serialize(self, obj):
        # Convert object to bytes
        return pickle.dumps(obj)
    
    def deserialize(self, data):
        # Convert bytes back to object
        return pickle.loads(data)
    
    def can_serialize(self, obj):
        # Check if this serializer can handle the object
        return isinstance(obj, MyModel)
```

## Appendix

### Supported Python Versions

- Python 3.7+
- PyPy 3.7+

### Supported Operating Systems

- Linux
- macOS
- Windows