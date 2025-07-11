"""Shared test fixtures and configuration."""

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest

from retainit.backends.disk import DiskCache
from retainit.backends.memory import MemoryCache
from retainit.serializers.registry import SerializerRegistry


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def memory_cache() -> AsyncGenerator[MemoryCache, None]:
    """Create a memory cache for testing."""
    cache = MemoryCache(max_size=100)
    try:
        yield cache
    finally:
        await cache.clear()


@pytest.fixture
async def disk_cache() -> AsyncGenerator[DiskCache, None]:
    """Create a disk cache for testing."""
    temp_dir = tempfile.mkdtemp()
    cache = DiskCache(base_directory=temp_dir)
    try:
        yield cache
    finally:
        await cache.clear()
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def serializer_registry() -> Generator[SerializerRegistry, None, None]:
    """Create a serializer registry for testing."""
    registry = SerializerRegistry()
    yield registry


@pytest.fixture
def sample_data():
    """Sample data for testing serialization."""
    return {
        "string": "hello world",
        "integer": 42,
        "float": 3.14159,
        "boolean": True,
        "none": None,
        "list": [1, 2, 3, "test"],
        "dict": {"key": "value", "number": 123},
        "nested": {"level1": {"level2": ["a", "b", "c"]}},
    }
