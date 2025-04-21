# retainit

A lightweight, extensible Python caching system for expensive function calls with support for various backends and data types.

[![PyPI](https://img.shields.io/pypi/v/retainit.svg)](https://pypi.org/project/retainit/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/retainit.svg)](https://pypi.org/project/retainit/)
[![Build Status](https://github.com/yourusername/retainit/workflows/retainit%20CI/CD/badge.svg)](https://github.com/yourusername/retainit/actions)
[![codecov](https://codecov.io/gh/yourusername/retainit/branch/main/graph/badge.svg)](https://codecov.io/gh/yourusername/retainit)
[![Documentation Status](https://readthedocs.org/projects/retainit/badge/?version=latest)](https://retainit.readthedocs.io/en/latest/?badge=latest)

## Features

- **Simple API**: Clean, intuitive decorator-based API
- **Multiple Storage Backends**: In-memory, disk, Redis, S3, DynamoDB
- **Async Support**: Fully compatible with asyncio
- **Specialized Data Type Handling**: Optimized for pandas, NumPy, Polars, etc.
- **Thread & Process Safe**: Robust concurrency handling
- **Framework Integration**: Works with FastAPI, Django, Flask
- **Metrics & Monitoring**: Built-in metrics collection with multiple backend support
- **Security**: Encryption options and secure configuration
- **Flexible Configuration**: Via code, environment variables, or config files

## Installation

Basic installation with memory and disk cache:

```bash
pip install retainit
```

With Redis support:

```bash
pip install retainit[redis]
```

With AWS support (S3, DynamoDB):

```bash
pip install retainit[aws]
```

With pandas/numpy/polars support:

```bash
pip install retainit[data]
```

Complete installation with all features:

```bash
pip install retainit[all]
```

## Quick Start

### Basic Usage

```python
from retainit import retain

@retain
def expensive_function(param):
    print(f"Computing result for {param}...")
    # Expensive operation
    return param * 2

# First call (cache miss)
result1 = expensive_function(42)  # Prints "Computing result for 42..."

# Second call (cache hit)
result2 = expensive_function(42)  # No print, returns cached result
```

### Async Support

```python
import asyncio
from retainit import retain

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

### Custom Cache Settings

```python
from retainit import retain

@retain(
    ttl=60,                     # 60 second time-to-live
    key_prefix="user_data",     # Custom key prefix
    exclude_args=["auth_token"] # Don't include in cache key
)
def get_user(user_id, auth_token):
    # Expensive API call
    return {"id": user_id, "name": "John Doe"}
```

### Global Configuration

```python
import retainit
from retainit import retain

# Configure globally
retainit.init(
    backend="redis",
    redis_url="redis://localhost:6379",
    ttl=300
)

# All decorated functions will use Redis
@retain
def get_data(id):
    # ...
```

### Predefined Environments

```python
import retainit
from retainit import retain

# Development configuration (memory cache, short TTL)
retainit.init_dev()

# Production configuration (Redis, compression, metrics)
retainit.init_prod(redis_url="redis://cache.example.com:6379")

# Testing configuration (small memory cache)
retainit.init_test()
```

## Cache Management

```python
from retainit import retain

@retain
def get_data(id):
    # ...

# Clear the entire cache
get_data.cache_clear()

# Delete a specific cache entry
get_data.cache_delete(42)
```

## Advanced Features

### Metrics Collection

```python
import retainit
from retainit import retain
from prometheus_client import start_http_server

# Enable Prometheus metrics
retainit.init(
    enable_metrics=True,
    metrics_backend="prometheus",
    metrics_namespace="myapp"
)

# Start Prometheus HTTP server
start_http_server(8000)

@retain
def tracked_function(param):
    # Function calls will be tracked in metrics
    return param * 2
```

### Framework Integration

#### FastAPI

```python
from fastapi import FastAPI
from retainit.ext.fastapi import setup_retainit
from retainit import retain

app = FastAPI()

# Set up retainit with FastAPI
setup_retainit(app, backend="redis", redis_url="redis://localhost:6379")

@app.get("/users/{user_id}")
@retain(ttl=30)
async def get_user(user_id: int):
    # Implementation
    return {"id": user_id, "name": "Example User"}
```

## Documentation

Full documentation is available at [https://retainit.readthedocs.io/](https://retainit.readthedocs.io/)

## Contributing

Contributions are welcome! Please check out our [Contributing Guide](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.