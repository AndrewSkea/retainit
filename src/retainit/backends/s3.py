"""AWS S3 cache backend implementation.

This module implements a cache backend that stores cached values in Amazon S3.
It supports TTL through object metadata and provides compression for large objects.
"""

import json
import logging
import time
from typing import Any, Optional

from ..exceptions import BackendError, BackendNotAvailableError
from ..serializers.registry import get_serializer
from ..settings import settings
from .base import CacheBackend

logger = logging.getLogger("retainit.backends.s3")


class S3Cache(CacheBackend[Any]):
    """S3-based cache backend.

    This backend stores cached values as objects in an S3 bucket.
    Each cached value is stored with metadata indicating its expiration time.

    Attributes:
        bucket: S3 bucket name for storing cached objects.
        prefix: Key prefix for all cached objects.
        region: AWS region for the S3 bucket.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "retainit",
        region: str = "us-east-1",
        **kwargs: Any,
    ) -> None:
        """Initialize the S3 cache backend.

        Args:
            bucket: S3 bucket name for storing cached objects.
            prefix: Key prefix for all cached objects. Defaults to "retainit".
            region: AWS region for the S3 bucket. Defaults to "us-east-1".
            **kwargs: Additional arguments passed to the S3 client.

        Raises:
            BackendNotAvailableError: If required dependencies are not available.
        """
        try:
            import aioboto3
        except ImportError as e:
            raise BackendNotAvailableError(
                "S3 backend requires 'aioboto3' package. "
                "Install with 'pip install retainit[aws]'",
                context={"import_error": str(e)},
            ) from e

        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.region = region
        self._session = aioboto3.Session()
        self._client_kwargs = kwargs

        logger.info(
            f"Initialized S3 cache with bucket={bucket}, prefix={prefix}, region={region}"
        )

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from the S3 cache.

        Args:
            key: The cache key to retrieve.

        Returns:
            The cached value, or None if not found or expired.

        Raises:
            BackendError: If the S3 operation fails.
        """
        try:
            s3_key = self._build_s3_key(key)

            async with self._session.client(
                "s3", region_name=self.region, **self._client_kwargs
            ) as s3:
                try:
                    response = await s3.get_object(Bucket=self.bucket, Key=s3_key)
                except Exception as e:
                    if (
                        hasattr(e, "response")
                        and e.response.get("Error", {}).get("Code") == "NoSuchKey"
                    ):
                        logger.debug(f"S3 cache miss for key: {key}")
                        return None
                    raise BackendError(f"Failed to get object from S3: {e}") from e

                # Check TTL
                metadata = response.get("Metadata", {})
                expires_at_str = metadata.get("expires-at")
                if expires_at_str:
                    try:
                        expires_at = float(expires_at_str)
                        if time.time() > expires_at:
                            logger.debug(f"S3 cache entry expired for key: {key}")
                            # Object has expired, delete it asynchronously
                            try:
                                await s3.delete_object(Bucket=self.bucket, Key=s3_key)
                            except Exception as delete_error:
                                logger.warning(
                                    f"Failed to delete expired S3 object: {delete_error}"
                                )
                            return None
                    except (ValueError, TypeError) as parse_error:
                        logger.warning(
                            f"Invalid expiration timestamp in S3 metadata: {parse_error}"
                        )

                # Read and deserialize the object
                body = await response["Body"].read()

                serializer_name = metadata.get("serializer", "json")
                serializer = get_serializer(serializer_name)

                try:
                    value = serializer.deserialize(body)
                    logger.debug(f"S3 cache hit for key: {key}")
                    return value
                except Exception as deserialize_error:
                    logger.error(
                        f"Failed to deserialize S3 object: {deserialize_error}"
                    )
                    raise BackendError(
                        f"Failed to deserialize cached value: {deserialize_error}"
                    ) from deserialize_error

        except BackendError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting S3 cache key {key}: {e}")
            raise BackendError(f"S3 cache get operation failed: {e}") from e

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in the S3 cache.

        Args:
            key: The cache key to set.
            value: The value to cache.
            ttl: Time to live in seconds. If None, the value will not expire.

        Raises:
            BackendError: If the S3 operation fails.
        """
        try:
            s3_key = self._build_s3_key(key)

            # Serialize the value
            serializer = get_serializer(settings.serializer.value)
            serialized_data = serializer.serialize(value)

            # Prepare metadata
            metadata = {
                "serializer": settings.serializer.value,
                "cached-at": str(time.time()),
            }

            if ttl is not None and ttl > 0:
                expires_at = time.time() + ttl
                metadata["expires-at"] = str(expires_at)

            async with self._session.client(
                "s3", region_name=self.region, **self._client_kwargs
            ) as s3:
                await s3.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=serialized_data,
                    Metadata=metadata,
                    ContentType="application/octet-stream",
                )

            logger.debug(f"S3 cache set for key: {key}")

        except Exception as e:
            logger.error(f"Failed to set S3 cache key {key}: {e}")
            raise BackendError(f"S3 cache set operation failed: {e}") from e

    async def delete(self, key: str) -> None:
        """Delete a value from the S3 cache.

        Args:
            key: The cache key to delete.

        Raises:
            BackendError: If the S3 operation fails.
        """
        try:
            s3_key = self._build_s3_key(key)

            async with self._session.client(
                "s3", region_name=self.region, **self._client_kwargs
            ) as s3:
                await s3.delete_object(Bucket=self.bucket, Key=s3_key)

            logger.debug(f"S3 cache delete for key: {key}")

        except Exception as e:
            logger.error(f"Failed to delete S3 cache key {key}: {e}")
            raise BackendError(f"S3 cache delete operation failed: {e}") from e

    async def clear(self) -> None:
        """Clear all cached values from the S3 bucket (with the configured prefix).

        This method deletes all objects in the bucket that start with the configured prefix.

        Raises:
            BackendError: If the S3 operation fails.
        """
        try:
            async with self._session.client(
                "s3", region_name=self.region, **self._client_kwargs
            ) as s3:
                # List all objects with the prefix
                paginator = s3.get_paginator("list_objects_v2")

                async for page in paginator.paginate(
                    Bucket=self.bucket, Prefix=self.prefix
                ):
                    contents = page.get("Contents", [])
                    if not contents:
                        continue

                    # Delete objects in batches
                    objects_to_delete = [{"Key": obj["Key"]} for obj in contents]

                    if objects_to_delete:
                        await s3.delete_objects(
                            Bucket=self.bucket, Delete={"Objects": objects_to_delete}
                        )

            logger.info(f"S3 cache cleared for prefix: {self.prefix}")

        except Exception as e:
            logger.error(f"Failed to clear S3 cache: {e}")
            raise BackendError(f"S3 cache clear operation failed: {e}") from e

    async def close(self) -> None:
        """Close any resources associated with the S3 cache.

        This method cleans up any resources, though aioboto3 handles
        most cleanup automatically.
        """
        # aioboto3 handles cleanup automatically via context managers
        logger.debug("S3 cache backend closed")

    def _build_s3_key(self, cache_key: str) -> str:
        """Build an S3 object key from a cache key.

        Args:
            cache_key: The cache key.

        Returns:
            The S3 object key.
        """
        # Ensure the key is safe for S3
        safe_key = cache_key.replace(" ", "_").replace("/", "_")
        return f"{self.prefix}/{safe_key}"
