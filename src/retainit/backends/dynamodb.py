"""AWS DynamoDB cache backend implementation.

This module implements a cache backend that stores cached values in Amazon DynamoDB.
It supports TTL through DynamoDB's built-in TTL feature and provides efficient
key-value storage with consistent performance.
"""

import base64
import logging
import time
from typing import Any, Dict, Optional

from ..exceptions import BackendError, BackendNotAvailableError
from ..serializers.registry import get_serializer
from ..settings import settings
from .base import CacheBackend

logger = logging.getLogger("retainit.backends.dynamodb")


class DynamoDBCache(CacheBackend[Any]):
    """DynamoDB-based cache backend.

    This backend stores cached values in a DynamoDB table with the following schema:
    - cache_key (String, Hash Key): The cache key
    - value (Binary): The serialized cached value
    - expires_at (Number, TTL): Unix timestamp when the item expires
    - created_at (Number): Unix timestamp when the item was created
    - serializer (String): Name of the serializer used

    Attributes:
        table: DynamoDB table name for storing cached items.
        region: AWS region for the DynamoDB table.
    """

    def __init__(
        self,
        table: str,
        region: str = "us-east-1",
        **kwargs: Any,
    ) -> None:
        """Initialize the DynamoDB cache backend.

        Args:
            table: DynamoDB table name for storing cached items.
            region: AWS region for the DynamoDB table. Defaults to "us-east-1".
            **kwargs: Additional arguments passed to the DynamoDB client.

        Raises:
            BackendNotAvailableError: If required dependencies are not available.
        """
        try:
            import aioboto3
        except ImportError as e:
            raise BackendNotAvailableError(
                "DynamoDB backend requires 'aioboto3' package. "
                "Install with 'pip install retainit[aws]'",
                context={"import_error": str(e)},
            ) from e

        self.table = table
        self.region = region
        self._session = aioboto3.Session()
        self._client_kwargs = kwargs

        logger.info(f"Initialized DynamoDB cache with table={table}, region={region}")

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from the DynamoDB cache.

        Args:
            key: The cache key to retrieve.

        Returns:
            The cached value, or None if not found or expired.

        Raises:
            BackendError: If the DynamoDB operation fails.
        """
        try:
            async with self._session.resource(
                "dynamodb", region_name=self.region, **self._client_kwargs
            ) as dynamodb:
                table = await dynamodb.Table(self.table)

                try:
                    response = await table.get_item(Key={"cache_key": key})
                except Exception as e:
                    raise BackendError(f"Failed to get item from DynamoDB: {e}") from e

                item = response.get("Item")
                if not item:
                    logger.debug(f"DynamoDB cache miss for key: {key}")
                    return None

                # Check TTL (DynamoDB automatically removes expired items, but check for consistency)
                expires_at = item.get("expires_at")
                if expires_at and time.time() > expires_at:
                    logger.debug(f"DynamoDB cache entry expired for key: {key}")
                    return None

                # Deserialize the value
                try:
                    serializer_name = item.get("serializer", "json")
                    serializer = get_serializer(serializer_name)

                    # DynamoDB stores binary data as base64-encoded strings in some cases
                    value_data = item["value"]
                    if isinstance(value_data, str):
                        value_data = base64.b64decode(value_data)
                    elif hasattr(value_data, "value"):
                        # boto3 Binary type
                        value_data = value_data.value

                    value = serializer.deserialize(value_data)
                    logger.debug(f"DynamoDB cache hit for key: {key}")
                    return value

                except Exception as deserialize_error:
                    logger.error(
                        f"Failed to deserialize DynamoDB item: {deserialize_error}"
                    )
                    raise BackendError(
                        f"Failed to deserialize cached value: {deserialize_error}"
                    ) from deserialize_error

        except BackendError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting DynamoDB cache key {key}: {e}")
            raise BackendError(f"DynamoDB cache get operation failed: {e}") from e

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in the DynamoDB cache.

        Args:
            key: The cache key to set.
            value: The value to cache.
            ttl: Time to live in seconds. If None, the value will not expire.

        Raises:
            BackendError: If the DynamoDB operation fails.
        """
        try:
            # Serialize the value
            serializer = get_serializer(settings.serializer.value)
            serialized_data = serializer.serialize(value)

            # Prepare the item
            item: Dict[str, Any] = {
                "cache_key": key,
                "value": serialized_data,
                "created_at": int(time.time()),
                "serializer": settings.serializer.value,
            }

            if ttl is not None and ttl > 0:
                expires_at = int(time.time() + ttl)
                item["expires_at"] = expires_at

            async with self._session.resource(
                "dynamodb", region_name=self.region, **self._client_kwargs
            ) as dynamodb:
                table = await dynamodb.Table(self.table)

                await table.put_item(Item=item)

            logger.debug(f"DynamoDB cache set for key: {key}")

        except Exception as e:
            logger.error(f"Failed to set DynamoDB cache key {key}: {e}")
            raise BackendError(f"DynamoDB cache set operation failed: {e}") from e

    async def delete(self, key: str) -> None:
        """Delete a value from the DynamoDB cache.

        Args:
            key: The cache key to delete.

        Raises:
            BackendError: If the DynamoDB operation fails.
        """
        try:
            async with self._session.resource(
                "dynamodb", region_name=self.region, **self._client_kwargs
            ) as dynamodb:
                table = await dynamodb.Table(self.table)

                await table.delete_item(Key={"cache_key": key})

            logger.debug(f"DynamoDB cache delete for key: {key}")

        except Exception as e:
            logger.error(f"Failed to delete DynamoDB cache key {key}: {e}")
            raise BackendError(f"DynamoDB cache delete operation failed: {e}") from e

    async def clear(self) -> None:
        """Clear all cached values from the DynamoDB table.

        This method scans the entire table and deletes all items.
        Warning: This can be expensive for large tables.

        Raises:
            BackendError: If the DynamoDB operation fails.
        """
        try:
            async with self._session.resource(
                "dynamodb", region_name=self.region, **self._client_kwargs
            ) as dynamodb:
                table = await dynamodb.Table(self.table)

                # Scan the table and delete all items
                scan_kwargs = {
                    "ProjectionExpression": "cache_key",
                }

                items_deleted = 0

                while True:
                    response = await table.scan(**scan_kwargs)
                    items = response.get("Items", [])

                    if not items:
                        break

                    # Delete items in batches
                    async with table.batch_writer() as batch:
                        for item in items:
                            await batch.delete_item(
                                Key={"cache_key": item["cache_key"]}
                            )
                            items_deleted += 1

                    # Check if there are more items to scan
                    last_evaluated_key = response.get("LastEvaluatedKey")
                    if not last_evaluated_key:
                        break

                    scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

            logger.info(f"DynamoDB cache cleared, deleted {items_deleted} items")

        except Exception as e:
            logger.error(f"Failed to clear DynamoDB cache: {e}")
            raise BackendError(f"DynamoDB cache clear operation failed: {e}") from e

    async def close(self) -> None:
        """Close any resources associated with the DynamoDB cache.

        This method cleans up any resources, though aioboto3 handles
        most cleanup automatically.
        """
        # aioboto3 handles cleanup automatically via context managers
        logger.debug("DynamoDB cache backend closed")

    async def health_check(self) -> bool:
        """Check if the DynamoDB table is accessible.

        Returns:
            True if the table is accessible, False otherwise.
        """
        try:
            async with self._session.client(
                "dynamodb", region_name=self.region, **self._client_kwargs
            ) as dynamodb:
                await dynamodb.describe_table(TableName=self.table)
                return True
        except Exception as e:
            logger.error(f"DynamoDB health check failed: {e}")
            return False
