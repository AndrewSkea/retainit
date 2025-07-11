"""Redis cache backend implementation."""

import asyncio
import logging
from typing import Any, Optional

from ..exceptions import BackendConnectionError, BackendError, BackendTimeoutError
from ..serializers.registry import get_registry
from ..validation import validate_cache_key, validate_ttl
from .base import CacheBackend

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as redis
    from redis.exceptions import ConnectionError, RedisError, TimeoutError

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    RedisError = ConnectionError = TimeoutError = Exception


class RedisCache(CacheBackend[Any]):
    """Redis cache backend.

    This backend provides distributed caching using Redis as the storage layer.
    It supports TTL, connection pooling, and automatic reconnection.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        password: Optional[str] = None,
        db: int = 0,
        ssl: bool = False,
        ssl_cert_reqs: Optional[str] = None,
        ssl_ca_certs: Optional[str] = None,
        ssl_certfile: Optional[str] = None,
        ssl_keyfile: Optional[str] = None,
        max_connections: int = 50,
        retry_on_timeout: bool = True,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        health_check_interval: int = 30,
        encoding: str = "utf-8",
        decode_responses: bool = False,
    ) -> None:
        """Initialize the Redis cache backend.

        Args:
            url: Redis connection URL.
            password: Optional password for authentication.
            db: Database number to use.
            ssl: Whether to use SSL/TLS.
            ssl_cert_reqs: SSL certificate requirements.
            ssl_ca_certs: Path to CA certificates file.
            ssl_certfile: Path to client certificate file.
            ssl_keyfile: Path to client private key file.
            max_connections: Maximum number of connections in the pool.
            retry_on_timeout: Whether to retry on timeout.
            socket_timeout: Socket timeout in seconds.
            socket_connect_timeout: Socket connection timeout in seconds.
            health_check_interval: Health check interval in seconds.
            encoding: String encoding to use.
            decode_responses: Whether to decode responses automatically.

        Raises:
            ImportError: If redis package is not available.
            BackendConnectionError: If connection to Redis fails.
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis package is required for RedisCache. "
                "Install with: pip install retainit[redis]"
            )

        self._url = url
        self._password = password
        self._db = db
        self._ssl = ssl
        self._ssl_cert_reqs = ssl_cert_reqs
        self._ssl_ca_certs = ssl_ca_certs
        self._ssl_certfile = ssl_certfile
        self._ssl_keyfile = ssl_keyfile
        self._max_connections = max_connections
        self._retry_on_timeout = retry_on_timeout
        self._socket_timeout = socket_timeout
        self._socket_connect_timeout = socket_connect_timeout
        self._health_check_interval = health_check_interval
        self._encoding = encoding
        self._decode_responses = decode_responses

        self._redis: Optional[redis.Redis] = None
        self._connection_pool: Optional[redis.ConnectionPool] = None
        self._serializer_registry = get_registry()
        self._connected = False
        self._connection_lock = asyncio.Lock()

    async def _ensure_connected(self) -> None:
        """Ensure connection to Redis is established."""
        if self._connected and self._redis is not None:
            return

        async with self._connection_lock:
            if self._connected and self._redis is not None:
                return

            try:
                # Create connection pool
                self._connection_pool = redis.ConnectionPool.from_url(
                    self._url,
                    password=self._password,
                    db=self._db,
                    ssl=self._ssl,
                    ssl_cert_reqs=self._ssl_cert_reqs,
                    ssl_ca_certs=self._ssl_ca_certs,
                    ssl_certfile=self._ssl_certfile,
                    ssl_keyfile=self._ssl_keyfile,
                    max_connections=self._max_connections,
                    retry_on_timeout=self._retry_on_timeout,
                    socket_timeout=self._socket_timeout,
                    socket_connect_timeout=self._socket_connect_timeout,
                    health_check_interval=self._health_check_interval,
                    encoding=self._encoding,
                    decode_responses=self._decode_responses,
                )

                # Create Redis client
                self._redis = redis.Redis(connection_pool=self._connection_pool)

                # Test connection
                await asyncio.wait_for(
                    self._redis.ping(), timeout=self._socket_connect_timeout
                )

                self._connected = True
                logger.info(f"Successfully connected to Redis at {self._url}")

            except (ConnectionError, TimeoutError) as e:
                logger.error(f"Failed to connect to Redis at {self._url}: {e}")
                raise BackendConnectionError(
                    f"Failed to connect to Redis: {e}",
                    context={"url": self._url, "error": str(e)},
                ) from e
            except Exception as e:
                logger.error(f"Unexpected error connecting to Redis: {e}")
                raise BackendError(
                    f"Unexpected Redis connection error: {e}",
                    context={"url": self._url, "error": str(e)},
                ) from e

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from the Redis cache.

        Args:
            key: The cache key to retrieve.

        Returns:
            The cached value, or None if not found.

        Raises:
            BackendError: If the operation fails.
        """
        validate_cache_key(key)
        await self._ensure_connected()

        try:
            # Get the serialized data and metadata
            pipe = self._redis.pipeline()
            pipe.hget(key, "data")
            pipe.hget(key, "serializer")
            pipe.hget(key, "metadata")

            results = await asyncio.wait_for(
                pipe.execute(), timeout=self._socket_timeout
            )

            data, serializer_name, metadata = results

            if data is None:
                logger.debug(f"Cache miss for key: {key}")
                return None

            # Deserialize the data
            if serializer_name is None:
                serializer_name = "json"  # Default fallback
            else:
                serializer_name = serializer_name.decode("utf-8")

            try:
                value = self._serializer_registry.deserialize(data, serializer_name)
                logger.debug(f"Cache hit for key: {key}")
                return value
            except Exception as e:
                logger.error(f"Failed to deserialize cached data for key {key}: {e}")
                # Remove corrupted data
                await self.delete(key)
                return None

        except TimeoutError as e:
            logger.error(f"Redis operation timed out for key {key}: {e}")
            raise BackendTimeoutError(
                f"Redis get operation timed out: {e}",
                context={"key": key, "timeout": self._socket_timeout},
            ) from e
        except RedisError as e:
            logger.error(f"Redis error during get operation for key {key}: {e}")
            raise BackendError(
                f"Redis get operation failed: {e}",
                context={"key": key, "error": str(e)},
            ) from e

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in the Redis cache.

        Args:
            key: The cache key to set.
            value: The value to cache.
            ttl: Optional time-to-live in seconds.

        Raises:
            BackendError: If the operation fails.
        """
        validate_cache_key(key)
        if ttl is not None:
            validate_ttl(ttl)

        await self._ensure_connected()

        try:
            # Serialize the value
            data, serializer_name = self._serializer_registry.serialize(value)

            # Create metadata
            metadata = {
                "type": type(value).__name__,
                "serializer": serializer_name,
            }

            # Store data with metadata
            pipe = self._redis.pipeline()
            pipe.hset(
                key,
                mapping={
                    "data": data,
                    "serializer": serializer_name,
                    "metadata": str(metadata),
                },
            )

            if ttl is not None:
                pipe.expire(key, ttl)

            await asyncio.wait_for(pipe.execute(), timeout=self._socket_timeout)

            logger.debug(f"Successfully cached value for key: {key}")

        except TimeoutError as e:
            logger.error(f"Redis operation timed out for key {key}: {e}")
            raise BackendTimeoutError(
                f"Redis set operation timed out: {e}",
                context={"key": key, "timeout": self._socket_timeout},
            ) from e
        except RedisError as e:
            logger.error(f"Redis error during set operation for key {key}: {e}")
            raise BackendError(
                f"Redis set operation failed: {e}",
                context={"key": key, "error": str(e)},
            ) from e

    async def delete(self, key: str) -> None:
        """Delete a value from the Redis cache.

        Args:
            key: The cache key to delete.

        Raises:
            BackendError: If the operation fails.
        """
        validate_cache_key(key)
        await self._ensure_connected()

        try:
            result = await asyncio.wait_for(
                self._redis.delete(key), timeout=self._socket_timeout
            )

            if result:
                logger.debug(f"Successfully deleted key: {key}")
            else:
                logger.debug(f"Key not found for deletion: {key}")

        except TimeoutError as e:
            logger.error(f"Redis operation timed out for key {key}: {e}")
            raise BackendTimeoutError(
                f"Redis delete operation timed out: {e}",
                context={"key": key, "timeout": self._socket_timeout},
            ) from e
        except RedisError as e:
            logger.error(f"Redis error during delete operation for key {key}: {e}")
            raise BackendError(
                f"Redis delete operation failed: {e}",
                context={"key": key, "error": str(e)},
            ) from e

    async def clear(self) -> None:
        """Clear all values from the Redis cache.

        Warning: This will delete ALL keys in the configured Redis database.

        Raises:
            BackendError: If the operation fails.
        """
        await self._ensure_connected()

        try:
            result = await asyncio.wait_for(
                self._redis.flushdb(),
                timeout=self._socket_timeout * 2,  # Give more time for clear
            )

            logger.info("Successfully cleared Redis cache")

        except TimeoutError as e:
            logger.error(f"Redis clear operation timed out: {e}")
            raise BackendTimeoutError(
                f"Redis clear operation timed out: {e}",
                context={"timeout": self._socket_timeout * 2},
            ) from e
        except RedisError as e:
            logger.error(f"Redis error during clear operation: {e}")
            raise BackendError(
                f"Redis clear operation failed: {e}", context={"error": str(e)}
            ) from e

    async def close(self) -> None:
        """Close the Redis connection and clean up resources."""
        if self._redis is not None:
            try:
                await self._redis.close()
                logger.debug("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")

        if self._connection_pool is not None:
            try:
                await self._connection_pool.disconnect()
                logger.debug("Redis connection pool disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting Redis connection pool: {e}")

        self._redis = None
        self._connection_pool = None
        self._connected = False

    async def ping(self) -> bool:
        """Check if the Redis connection is healthy.

        Returns:
            True if the connection is healthy, False otherwise.
        """
        try:
            await self._ensure_connected()
            await asyncio.wait_for(self._redis.ping(), timeout=self._socket_timeout)
            return True
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False

    async def info(self) -> dict[str, Any]:
        """Get Redis server information.

        Returns:
            A dictionary containing Redis server information.

        Raises:
            BackendError: If the operation fails.
        """
        await self._ensure_connected()

        try:
            info = await asyncio.wait_for(
                self._redis.info(), timeout=self._socket_timeout
            )
            return dict(info)
        except Exception as e:
            logger.error(f"Failed to get Redis info: {e}")
            raise BackendError(
                f"Failed to get Redis info: {e}", context={"error": str(e)}
            ) from e
