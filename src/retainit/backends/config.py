"""Backend configuration classes for retainit.

This module provides strongly-typed configuration classes for the different
cache backends supported by retainit.
"""

from dataclasses import dataclass
from typing import Union


@dataclass
class BackendConfig:
    """Base class for all backend configurations.

    This class defines common configuration options for all cache backends.

    Attributes:
        ttl: Default time-to-live for cached values in seconds.
            If None, cached values will not expire.
        compression: Whether to compress cached values.

    """

    ttl: int | None = None
    compression: bool = False


@dataclass
class MemoryConfig(BackendConfig):
    """Configuration for in-memory cache backend.

    This backend stores cached values in memory using a dictionary with
    LRU (Least Recently Used) eviction policy.

    Attributes:
        max_size: Maximum number of items to store in the cache.
            If None, no limit is applied.

    """

    max_size: int | None = None


@dataclass
class DiskConfig(BackendConfig):
    """Configuration for disk-based cache backend.

    This backend stores cached values in files on disk.

    Attributes:
        base_path: Base directory where cache files are stored.

    """

    base_path: str = ".cache/function_resp"


@dataclass
class RedisConfig(BackendConfig):
    """Configuration for Redis cache backend.

    This backend stores cached values in a Redis server.

    Attributes:
        url: Redis connection URL.
        password: Redis password.
        ssl: Whether to use SSL for Redis connection.
        cert_reqs: SSL certificate requirements.
        ca_certs: Path to the CA certificate file.
        db: Redis database number.

    """

    url: str = "redis://localhost:6379"
    password: str | None = None
    ssl: bool = False
    cert_reqs: str | None = None
    ca_certs: str | None = None
    db: int = 0


@dataclass
class S3Config(BackendConfig):
    """Configuration for S3 cache backend.

    This backend stores cached values in an AWS S3 bucket.

    Attributes:
        bucket: S3 bucket name.
        prefix: Prefix for S3 keys.
        region: AWS region.
        aws_access_key_id: AWS access key ID.
        aws_secret_access_key: AWS secret access key.

    """

    bucket: str | None = None
    prefix: str = "retainit"
    region: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None


@dataclass
class DynamoDBConfig(BackendConfig):
    """Configuration for DynamoDB cache backend.

    This backend stores cached values in an AWS DynamoDB table.

    Attributes:
        table: DynamoDB table name.
        region: AWS region.
        aws_access_key_id: AWS access key ID.
        aws_secret_access_key: AWS secret access key.

    """

    table: str | None = None
    region: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None


# Type for all possible backend configs
BackendConfigType = Union[
    MemoryConfig,
    DiskConfig,
    RedisConfig,
    S3Config,
    DynamoDBConfig,
]
