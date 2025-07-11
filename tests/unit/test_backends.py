"""Tests for cache backends."""

import asyncio
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from retainit.backends.base import CacheBackend
from retainit.backends.disk import DiskCache
from retainit.backends.dynamodb import DynamoDBCache
from retainit.backends.memory import MemoryCache
from retainit.backends.redis import RedisCache
from retainit.backends.s3 import S3Cache
from retainit.exceptions import BackendError, BackendNotAvailableError


class TestMemoryCache:
    """Test cases for the MemoryCache backend."""

    @pytest.mark.asyncio
    async def test_memory_cache_basic_operations(self):
        """Test basic get/set/delete operations."""
        cache = MemoryCache(max_size=100)

        # Test cache miss
        result = await cache.get("key1")
        assert result is None

        # Test cache set and hit
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

        # Test cache delete
        await cache.delete("key1")
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_cache_ttl(self):
        """Test TTL functionality."""
        cache = MemoryCache(max_size=100)

        # Set with TTL
        await cache.set("key1", "value1", ttl=1)

        # Should be available immediately
        result = await cache.get("key1")
        assert result == "value1"

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_cache_lru_eviction(self):
        """Test LRU eviction when max size is reached."""
        cache = MemoryCache(max_size=2)

        # Fill the cache
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        # Access key1 to make it most recently used
        await cache.get("key1")

        # Add key3, should evict key2 (least recently used)
        await cache.set("key3", "value3")

        # key1 and key3 should exist, key2 should be evicted
        assert await cache.get("key1") == "value1"
        assert await cache.get("key3") == "value3"
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_memory_cache_clear(self):
        """Test cache clearing."""
        cache = MemoryCache(max_size=100)

        # Add some items
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        # Clear the cache
        await cache.clear()

        # All items should be gone
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_memory_cache_stats(self):
        """Test cache statistics."""
        cache = MemoryCache(max_size=100)

        # Initially empty
        stats = cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0

        # Add an item and access it
        await cache.set("key1", "value1")
        await cache.get("key1")  # Hit
        await cache.get("key2")  # Miss

        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1


class TestDiskCache:
    """Test cases for the DiskCache backend."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_disk_cache_basic_operations(self, temp_dir):
        """Test basic get/set/delete operations."""
        cache = DiskCache(base_directory=temp_dir)

        # Test cache miss
        result = await cache.get("key1")
        assert result is None

        # Test cache set and hit
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

        # Test cache delete
        await cache.delete("key1")
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_disk_cache_ttl(self, temp_dir):
        """Test TTL functionality."""
        cache = DiskCache(base_directory=temp_dir)

        # Set with TTL
        await cache.set("key1", "value1", ttl=1)

        # Should be available immediately
        result = await cache.get("key1")
        assert result == "value1"

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_disk_cache_compression(self, temp_dir):
        """Test compression functionality."""
        cache = DiskCache(base_directory=temp_dir, compression=True)

        # Test with compressible data
        large_data = "x" * 1000
        await cache.set("key1", large_data)
        result = await cache.get("key1")
        assert result == large_data

    @pytest.mark.asyncio
    async def test_disk_cache_clear(self, temp_dir):
        """Test cache clearing."""
        cache = DiskCache(base_directory=temp_dir)

        # Add some items
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        # Clear the cache
        await cache.clear()

        # All items should be gone
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_disk_cache_persistence(self, temp_dir):
        """Test that disk cache persists across instances."""
        # Create first cache instance and set a value
        cache1 = DiskCache(base_directory=temp_dir)
        await cache1.set("key1", "value1")

        # Create second cache instance and retrieve the value
        cache2 = DiskCache(base_directory=temp_dir)
        result = await cache2.get("key1")
        assert result == "value1"


class TestRedisCache:
    """Test cases for the RedisCache backend."""

    @pytest.mark.asyncio
    async def test_redis_cache_import_error(self):
        """Test that RedisCache raises appropriate error when redis is not available."""
        with patch.dict("sys.modules", {"redis": None}):
            with pytest.raises(
                BackendNotAvailableError, match="Redis backend requires 'redis' package"
            ):
                RedisCache(url="redis://localhost")

    @pytest.mark.asyncio
    async def test_redis_cache_basic_operations(self):
        """Test basic Redis operations with mock."""
        # Mock the redis module
        mock_redis = Mock()
        mock_client = AsyncMock()
        mock_redis.from_url.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis}):
            cache = RedisCache(url="redis://localhost")

            # Test cache miss
            mock_client.get.return_value = None
            result = await cache.get("key1")
            assert result is None

            # Test cache set
            mock_client.set.return_value = True
            await cache.set("key1", "value1")
            mock_client.set.assert_called_once()

            # Test cache hit
            mock_client.get.return_value = b'"value1"'  # JSON encoded
            result = await cache.get("key1")
            assert result == "value1"

            # Test cache delete
            mock_client.delete.return_value = 1
            await cache.delete("key1")
            mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_cache_ttl(self):
        """Test Redis TTL functionality with mock."""
        mock_redis = Mock()
        mock_client = AsyncMock()
        mock_redis.from_url.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis}):
            cache = RedisCache(url="redis://localhost")

            # Test set with TTL
            mock_client.set.return_value = True
            await cache.set("key1", "value1", ttl=60)

            # Verify set was called with TTL
            mock_client.set.assert_called_once()
            call_args = mock_client.set.call_args
            assert call_args[1]["ex"] == 60

    @pytest.mark.asyncio
    async def test_redis_cache_connection_error(self):
        """Test Redis connection error handling."""
        mock_redis = Mock()
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection failed")
        mock_redis.from_url.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis}):
            cache = RedisCache(url="redis://localhost")

            with pytest.raises(BackendError, match="Redis operation failed"):
                await cache.get("key1")


class TestS3Cache:
    """Test cases for the S3Cache backend."""

    @pytest.mark.asyncio
    async def test_s3_cache_import_error(self):
        """Test that S3Cache raises appropriate error when aioboto3 is not available."""
        with patch.dict("sys.modules", {"aioboto3": None}):
            with pytest.raises(
                BackendNotAvailableError, match="S3 backend requires 'aioboto3' package"
            ):
                S3Cache(bucket="test-bucket")

    @pytest.mark.asyncio
    async def test_s3_cache_basic_operations(self):
        """Test basic S3 operations with mock."""
        # Mock aioboto3
        mock_aioboto3 = Mock()
        mock_session = Mock()
        mock_client = AsyncMock()

        # Setup mock chain
        mock_aioboto3.Session.return_value = mock_session
        mock_session.client.return_value.__aenter__.return_value = mock_client

        with patch.dict("sys.modules", {"aioboto3": mock_aioboto3}):
            cache = S3Cache(bucket="test-bucket")

            # Test cache miss (NoSuchKey error)
            error = Exception()
            error.response = {"Error": {"Code": "NoSuchKey"}}
            mock_client.get_object.side_effect = error

            result = await cache.get("key1")
            assert result is None

            # Test cache set
            await cache.set("key1", "value1")
            mock_client.put_object.assert_called_once()

            # Test cache hit
            mock_response = {"Body": AsyncMock(), "Metadata": {"serializer": "json"}}
            mock_response["Body"].read.return_value = b'"value1"'  # JSON encoded
            mock_client.get_object.return_value = mock_response
            mock_client.get_object.side_effect = None  # Reset side effect

            result = await cache.get("key1")
            assert result == "value1"

    @pytest.mark.asyncio
    async def test_s3_cache_ttl_expiration(self):
        """Test S3 TTL expiration handling."""
        mock_aioboto3 = Mock()
        mock_session = Mock()
        mock_client = AsyncMock()

        mock_aioboto3.Session.return_value = mock_session
        mock_session.client.return_value.__aenter__.return_value = mock_client

        with patch.dict("sys.modules", {"aioboto3": mock_aioboto3}):
            cache = S3Cache(bucket="test-bucket")

            # Mock expired object
            import time

            expired_timestamp = str(time.time() - 3600)  # 1 hour ago
            mock_response = {
                "Body": AsyncMock(),
                "Metadata": {"serializer": "json", "expires-at": expired_timestamp},
            }
            mock_response["Body"].read.return_value = b'"value1"'
            mock_client.get_object.return_value = mock_response

            result = await cache.get("key1")
            assert result is None  # Should be None due to expiration

            # Should attempt to delete expired object
            mock_client.delete_object.assert_called_once()


class TestDynamoDBCache:
    """Test cases for the DynamoDBCache backend."""

    @pytest.mark.asyncio
    async def test_dynamodb_cache_import_error(self):
        """Test that DynamoDBCache raises appropriate error when aioboto3 is not available."""
        with patch.dict("sys.modules", {"aioboto3": None}):
            with pytest.raises(
                BackendNotAvailableError,
                match="DynamoDB backend requires 'aioboto3' package",
            ):
                DynamoDBCache(table="test-table")

    @pytest.mark.asyncio
    async def test_dynamodb_cache_basic_operations(self):
        """Test basic DynamoDB operations with mock."""
        # Mock aioboto3
        mock_aioboto3 = Mock()
        mock_session = Mock()
        mock_resource = Mock()
        mock_table = AsyncMock()

        # Setup mock chain
        mock_aioboto3.Session.return_value = mock_session
        mock_session.resource.return_value.__aenter__.return_value = mock_resource
        mock_resource.Table.return_value = mock_table

        with patch.dict("sys.modules", {"aioboto3": mock_aioboto3}):
            cache = DynamoDBCache(table="test-table")

            # Test cache miss
            mock_table.get_item.return_value = {}  # Empty response
            result = await cache.get("key1")
            assert result is None

            # Test cache set
            await cache.set("key1", "value1")
            mock_table.put_item.assert_called_once()

            # Test cache hit
            import time

            mock_table.get_item.return_value = {
                "Item": {
                    "cache_key": "key1",
                    "value": b'"value1"',  # JSON encoded bytes
                    "serializer": "json",
                    "created_at": int(time.time()),
                }
            }

            result = await cache.get("key1")
            assert result == "value1"

    @pytest.mark.asyncio
    async def test_dynamodb_cache_ttl_expiration(self):
        """Test DynamoDB TTL expiration handling."""
        mock_aioboto3 = Mock()
        mock_session = Mock()
        mock_resource = Mock()
        mock_table = AsyncMock()

        mock_aioboto3.Session.return_value = mock_session
        mock_session.resource.return_value.__aenter__.return_value = mock_resource
        mock_resource.Table.return_value = mock_table

        with patch.dict("sys.modules", {"aioboto3": mock_aioboto3}):
            cache = DynamoDBCache(table="test-table")

            # Mock expired item
            import time

            expired_timestamp = time.time() - 3600  # 1 hour ago
            mock_table.get_item.return_value = {
                "Item": {
                    "cache_key": "key1",
                    "value": b'"value1"',
                    "serializer": "json",
                    "expires_at": expired_timestamp,
                }
            }

            result = await cache.get("key1")
            assert result is None  # Should be None due to expiration

    @pytest.mark.asyncio
    async def test_dynamodb_cache_health_check(self):
        """Test DynamoDB health check functionality."""
        mock_aioboto3 = Mock()
        mock_session = Mock()
        mock_client = AsyncMock()

        mock_aioboto3.Session.return_value = mock_session
        mock_session.client.return_value.__aenter__.return_value = mock_client

        with patch.dict("sys.modules", {"aioboto3": mock_aioboto3}):
            cache = DynamoDBCache(table="test-table")

            # Test successful health check
            mock_client.describe_table.return_value = {
                "Table": {"TableName": "test-table"}
            }
            result = await cache.health_check()
            assert result is True

            # Test failed health check
            mock_client.describe_table.side_effect = Exception("Table not found")
            result = await cache.health_check()
            assert result is False


class TestCacheBackendInterface:
    """Test cases for the abstract CacheBackend interface."""

    def test_cache_backend_is_abstract(self):
        """Test that CacheBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            CacheBackend()

    def test_cache_backend_subclass_must_implement_methods(self):
        """Test that subclasses must implement all abstract methods."""

        class IncompleteCacheBackend(CacheBackend):
            pass  # Missing all abstract methods

        with pytest.raises(TypeError):
            IncompleteCacheBackend()

    @pytest.mark.asyncio
    async def test_cache_backend_close_default_implementation(self):
        """Test that the default close() implementation does nothing."""

        class MockCacheBackend(CacheBackend):
            async def get(self, key: str):
                return None

            async def set(self, key: str, value, ttl=None):
                pass

            async def delete(self, key: str):
                pass

            async def clear(self):
                pass

        backend = MockCacheBackend()
        await backend.close()  # Should not raise any exception
