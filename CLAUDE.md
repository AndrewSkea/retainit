# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`retainit` is a lightweight, extensible Python caching library for expensive function calls. It supports various backends (memory, disk, Redis, S3, DynamoDB) and provides a decorator-based API for caching function results with TTL support, event system, and comprehensive metrics collection.

## Development Commands

### Testing
```bash
# Run all tests
pytest tests -v

# Run unit tests only
pytest tests/unit -v --cov=retainit --cov-report=xml

# Run integration tests with mocks
pytest tests/integration -v --cov=retainit --cov-append --cov-report=xml

# Run performance benchmarks
pytest tests/performance -v --benchmark-json=benchmark.json

# Run with coverage
pytest tests -v --cov=retainit --cov-report=term-missing --cov-report=xml
```

### Linting and Code Quality
```bash
# Format code
black src tests

# Check formatting
black --check src tests

# Sort imports
isort src tests

# Check import sorting
isort --check src tests

# Lint with flake8
flake8 src tests

# Type checking
mypy src

# Security checks
bandit -r src

# Vulnerability checks
safety check

# Run all linting (recommended before committing)
black src tests && isort src tests && flake8 src tests && mypy src && bandit -r src
```

### Package Management
```bash
# Install development dependencies
pip install -e .[dev,test]

# Install all extras
pip install -e .[all]

# Build package
python -m build

# Check package
twine check dist/*
```

## Architecture

### Core Components

1. **`retain` Decorator (`core.py`)**: Main user-facing decorator that wraps functions for caching
2. **CacheManager (`core.py`)**: Coordinates cache operations and backend initialization
3. **Backend System (`backends/`)**: Abstract base class with multiple implementations
4. **Registry System (`registry.py`)**: Manages backend configurations and registration
5. **Event System (`events.py`)**: Pub/sub system for cache events and metrics
6. **Configuration System (`config.py`, `settings.py`)**: Handles settings from various sources

### Backend Architecture

The library uses a pluggable backend system:
- **MemoryCache**: In-memory LRU cache with size limits
- **DiskCache**: File-based cache with compression support
- **RedisCache**: Distributed cache using Redis
- **S3Cache**: Cloud storage cache using AWS S3
- **DynamoDBCache**: NoSQL cache using AWS DynamoDB

### Event System

The event system emits events for:
- Cache operations (hit, miss, set, delete, clear, error)
- Function calls (start, end, error)
- Backend lifecycle (init, close)

### Key Generation

Cache keys are generated using:
- Function module and qualified name
- Hashed function arguments (with exclusion support)
- Configurable prefixes
- MD5 hashing for consistent length

## Important Implementation Details

### Async/Sync Compatibility
- Supports both sync and async functions
- Uses `asyncio.iscoroutinefunction()` to detect async functions
- Sync functions run cache operations in event loop
- Requires `nest_asyncio` for nested event loop support

### Backend Registration
Functions can use specific backends via the registry:
```python
retainit.register_backend("my_redis", RedisConfig(...), default=True)

@retain(backend="my_redis")
def my_function():
    pass
```

### Configuration Precedence
1. Decorator arguments (highest priority)
2. Registered backends
3. Configuration files
4. Environment variables
5. Default values (lowest priority)

## Testing Strategy

- **Unit Tests**: Component isolation with 100% coverage goal
- **Integration Tests**: Mock backends and real backend integration
- **Performance Tests**: Benchmark suite with regression detection
- **Security Tests**: Penetration testing and fuzzing
- **Concurrency Tests**: Thread and process safety verification

## Development Notes

### Package Structure
- Core dependencies minimal (only `typing-extensions` for older Python)
- Optional dependencies via extras (`[redis]`, `[aws]`, `[data]`, etc.)
- Modular design allows selective feature installation

### Error Handling
- Comprehensive error logging with structured events
- Graceful degradation (cache failures don't break function execution)
- Circuit breaker pattern for repeated failures

### Performance Considerations
- Lazy backend initialization
- Efficient key generation with MD5 hashing
- Optional compression for large values
- Specialized serializers for data types (pandas, numpy, etc.)

## Common Development Patterns

### Adding New Backends
1. Inherit from `CacheBackend` in `backends/base.py`
2. Implement all abstract methods (`get`, `set`, `delete`, `clear`)
3. Add configuration class in `backends/config.py`
4. Register in `core.py` backend initialization
5. Add optional dependency in `pyproject.toml`

### Adding Event Handlers
Events are handled via the events system:
```python
from retainit.events import events, EventType

@events.on(EventType.CACHE_HIT)
def handle_cache_hit(event_data):
    # Handle the event
    pass
```

### Testing New Features
- Write unit tests in `tests/unit/`
- Add integration tests in `tests/integration/`
- Include performance benchmarks if applicable
- Ensure 100% test coverage for new code

## CI/CD Pipeline

The GitHub Actions workflow includes:
- Linting and type checking
- Multi-OS and multi-Python version testing
- Real backend integration tests
- Performance benchmarking
- Security scanning
- Package building and publishing

Tests run on Python 3.7-3.11 across Ubuntu, Windows, and macOS.