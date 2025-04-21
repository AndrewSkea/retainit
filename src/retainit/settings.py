"""Settings management for retainit.

This module provides the Settings class which encapsulates all configuration
options for retainit and handles validation and conversion of values.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Type, TypeVar, Union, cast

from .config import CacheBackendType, Config, config

logger = logging.getLogger("retainit.settings")


class MetricsBackendType(str, Enum):
    """Supported metrics backend types."""

    PROMETHEUS = "prometheus"
    DATADOG = "datadog"
    CLOUDWATCH = "cloudwatch"
    STATSD = "statsd"
    NONE = "none"


class SerializerType(str, Enum):
    """Supported serializer types."""

    PICKLE = "pickle"
    JSON = "json"
    STRING = "string"
    BYTES = "bytes"
    PANDAS = "pandas"
    NUMPY = "numpy"
    POLARS = "polars"
    ARROW = "arrow"
    MSGPACK = "msgpack"
    AUTO = "auto"  # Automatically select based on data type


@dataclass
class RedisSettings:
    """Redis backend settings."""

    url: str
    password: Optional[str] = None
    ssl: bool = False
    cert_reqs: Optional[str] = None
    ca_certs: Optional[str] = None


@dataclass
class S3Settings:
    """S3 backend settings."""

    bucket: str
    prefix: str = "retainit"
    region: Optional[str] = None


@dataclass
class DynamoDBSettings:
    """DynamoDB backend settings."""

    table: str
    region: Optional[str] = None


@dataclass
class MetricsSettings:
    """Metrics settings."""

    enabled: bool = False
    backend: Optional[MetricsBackendType] = None
    namespace: str = "retainit"


@dataclass
class CircuitBreakerSettings:
    """Circuit breaker settings."""

    enabled: bool = False
    threshold: int = 5
    timeout: int = 60


@dataclass
class Settings:
    """Main settings class for retainit.

    This class encapsulates all configuration options for retainit and provides
    validation and conversion of values.

    Attributes:
        backend: The cache backend to use.
        ttl: Default time-to-live for cached values in seconds.
        base_path: Base directory for disk cache.
        compression: Whether to compress cached values.
        key_prefix: Prefix for cache keys.
        max_size: Maximum number of items to store in memory cache.
        redis: Redis backend settings.
        s3: S3 backend settings.
        dynamodb: DynamoDB backend settings.
        metrics: Metrics settings.
        log_level: Logging level.
        encryption: Whether to encrypt cached values.
        encryption_key: Key for encrypting cached values.
        circuit_breaker: Circuit breaker settings.
        serializer: Default serializer to use.
    """

    backend: CacheBackendType = CacheBackendType.MEMORY
    ttl: Optional[int] = 3600
    base_path: str = ".cache/function_resp"
    compression: bool = False
    key_prefix: str = "retainit"
    max_size: Optional[int] = None

    # Backend-specific settings
    redis: Optional[RedisSettings] = None
    s3: Optional[S3Settings] = None
    dynamodb: Optional[DynamoDBSettings] = None

    # Metrics settings
    metrics: MetricsSettings = field(default_factory=MetricsSettings)

    # Logging settings
    log_level: str = "WARNING"

    # Security settings
    encryption: bool = False
    encryption_key: Optional[str] = None

    # Reliability settings
    circuit_breaker: CircuitBreakerSettings = field(default_factory=CircuitBreakerSettings)

    # Serialization settings
    serializer: SerializerType = SerializerType.AUTO

    @classmethod
    def from_config(cls, config_instance: Optional[Config] = None) -> "Settings":
        """Create a Settings instance from a Config object.

        Args:
            config_instance: The Config instance to use. If None, the global config is used.

        Returns:
            A new Settings instance with values from the config.
        """
        if config_instance is None:
            config_instance = config

        if not config_instance.is_initialized():
            logger.debug("Config not initialized, initializing with defaults")
            config_instance.init()

        # Get all configuration values
        config_dict = config_instance.get_all()

        # Create the settings object
        settings = cls(
            backend=CacheBackendType(config_dict.get("backend", CacheBackendType.MEMORY.value)),
            ttl=cast(Optional[int], config_dict.get("ttl")),
            base_path=cast(str, config_dict.get("base_path", ".cache/function_resp")),
            compression=cast(bool, config_dict.get("compression", False)),
            key_prefix=cast(str, config_dict.get("key_prefix", "retainit")),
            max_size=cast(Optional[int], config_dict.get("max_size")),
            log_level=cast(str, config_dict.get("log_level", "WARNING")),
            encryption=cast(bool, config_dict.get("encryption", False)),
            encryption_key=cast(Optional[str], config_dict.get("encryption_key")),
        )

        # Set backend-specific settings
        redis_url = config_dict.get("redis_url")
        if redis_url:
            settings.redis = RedisSettings(
                url=cast(str, redis_url),
                password=cast(Optional[str], config_dict.get("redis_password")),
                ssl=cast(bool, config_dict.get("redis_ssl", False)),
                cert_reqs=cast(Optional[str], config_dict.get("redis_cert_reqs")),
                ca_certs=cast(Optional[str], config_dict.get("redis_ca_certs")),
            )

        s3_bucket = config_dict.get("s3_bucket")
        if s3_bucket:
            settings.s3 = S3Settings(
                bucket=cast(str, s3_bucket),
                prefix=cast(str, config_dict.get("s3_prefix", "retainit")),
                region=cast(Optional[str], config_dict.get("s3_region")),
            )

        dynamodb_table = config_dict.get("dynamodb_table")
        if dynamodb_table:
            settings.dynamodb = DynamoDBSettings(
                table=cast(str, dynamodb_table),
                region=cast(Optional[str], config_dict.get("dynamodb_region")),
            )

        # Set metrics settings
        metrics_enabled = cast(bool, config_dict.get("enable_metrics", False))
        metrics_backend = config_dict.get("metrics_backend")
        if metrics_enabled and metrics_backend:
            settings.metrics = MetricsSettings(
                enabled=metrics_enabled,
                backend=MetricsBackendType(cast(str, metrics_backend)),
                namespace=cast(str, config_dict.get("metrics_namespace", "retainit")),
            )
        else:
            settings.metrics = MetricsSettings(enabled=metrics_enabled)

        # Set circuit breaker settings
        circuit_breaker_enabled = cast(bool, config_dict.get("circuit_breaker", False))
        if circuit_breaker_enabled:
            settings.circuit_breaker = CircuitBreakerSettings(
                enabled=circuit_breaker_enabled,
                threshold=cast(int, config_dict.get("circuit_breaker_threshold", 5)),
                timeout=cast(int, config_dict.get("circuit_breaker_timeout", 60)),
            )
        else:
            settings.circuit_breaker = CircuitBreakerSettings(enabled=False)

        # Set serializer
        serializer = config_dict.get("serializer", "auto")
        if serializer:
            settings.serializer = SerializerType(cast(str, serializer))

        return settings

    def validate(self) -> None:
        """Validate the settings.

        Raises:
            ValueError: If the settings are invalid.
        """
        # Validate backend requirements
        if self.backend == CacheBackendType.REDIS and not self.redis:
            raise ValueError("Redis settings must be provided when using Redis backend")
        elif self.backend == CacheBackendType.S3 and not self.s3:
            raise ValueError("S3 settings must be provided when using S3 backend")
        elif self.backend == CacheBackendType.DYNAMODB and not self.dynamodb:
            raise ValueError("DynamoDB settings must be provided when using DynamoDB backend")

        # Validate metrics settings
        if self.metrics.enabled and not self.metrics.backend:
            raise ValueError("Metrics backend must be specified when metrics are enabled")

        # Validate encryption settings
        if self.encryption and not self.encryption_key:
            raise ValueError("Encryption key must be specified when encryption is enabled")

        # Validate TTL
        if self.ttl is not None and self.ttl <= 0:
            raise ValueError("TTL must be positive")

        # Validate max_size
        if self.max_size is not None and self.max_size <= 0:
            raise ValueError("Max size must be positive")

        # Validate circuit breaker settings
        if self.circuit_breaker.enabled:
            if self.circuit_breaker.threshold <= 0:
                raise ValueError("Circuit breaker threshold must be positive")
            if self.circuit_breaker.timeout <= 0:
                raise ValueError("Circuit breaker timeout must be positive")


# Global settings instance
settings = Settings.from_config()


def init_settings(**kwargs: Any) -> Settings:
    """Initialize the global settings with custom values.

    Args:
        **kwargs: Custom settings values.

    Returns:
        The updated settings instance.
    """
    global settings

    # Initialize the config with the provided values
    config.init(**kwargs)

    # Create new settings from the updated config
    settings = Settings.from_config()

    return settings