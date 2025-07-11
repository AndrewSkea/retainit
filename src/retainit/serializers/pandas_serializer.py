"""Pandas serializer for DataFrame and Series objects.

This serializer provides efficient serialization for pandas DataFrames and Series
using multiple formats (parquet, pickle, feather) with compression support.
"""

import logging
from io import BytesIO
from typing import Any, Type, TypeVar

from ..exceptions import BackendNotAvailableError, SerializationError
from .base import Serializer

logger = logging.getLogger("retainit.serializers.pandas")

T = TypeVar("T")


class PandasSerializer(Serializer):
    """Pandas-specific serializer for DataFrames and Series.

    This serializer can handle pandas DataFrames and Series using different
    storage formats optimized for performance and compression.

    Attributes:
        format: Storage format to use ('parquet', 'pickle', 'feather').
        compression: Compression algorithm to use.
    """

    def __init__(self, format: str = "parquet", compression: str = "snappy") -> None:
        """Initialize the pandas serializer.

        Args:
            format: Storage format to use ('parquet', 'pickle', 'feather').
            compression: Compression algorithm to use.

        Raises:
            BackendNotAvailableError: If pandas is not available.
        """
        try:
            import pandas as pd

            self.pd = pd
        except ImportError as e:
            raise BackendNotAvailableError(
                "Pandas serializer requires 'pandas' package. "
                "Install with 'pip install retainit[pandas]'",
                context={"import_error": str(e)},
            ) from e

        if format not in ["parquet", "pickle", "feather"]:
            raise ValueError(f"Unsupported format: {format}")

        self.format = format
        self.compression = compression

    @property
    def name(self) -> str:
        """Return the name of this serializer."""
        return f"pandas_{self.format}"

    @property
    def content_type(self) -> str:
        """Return the MIME content type for this serializer."""
        if self.format == "parquet":
            return "application/parquet"
        elif self.format == "feather":
            return "application/arrow"
        else:
            return "application/python-pickle"

    def can_serialize(self, obj: Any) -> bool:
        """Check if this serializer can handle the given object.

        Args:
            obj: The object to check.

        Returns:
            True if this serializer can handle the object, False otherwise.
        """
        return isinstance(obj, (self.pd.DataFrame, self.pd.Series))

    def serialize(self, obj: Any) -> bytes:
        """Serialize a pandas object to bytes.

        Args:
            obj: The pandas object to serialize.

        Returns:
            The serialized data as bytes.

        Raises:
            SerializationError: If serialization fails.
        """
        if not self.can_serialize(obj):
            raise SerializationError(
                f"Object of type {type(obj).__name__} cannot be serialized by pandas serializer"
            )

        try:
            buffer = BytesIO()

            if self.format == "parquet":
                if isinstance(obj, self.pd.Series):
                    # Convert Series to DataFrame for parquet compatibility
                    df = obj.to_frame()
                    df.to_parquet(buffer, compression=self.compression)
                else:
                    obj.to_parquet(buffer, compression=self.compression)

            elif self.format == "feather":
                if isinstance(obj, self.pd.Series):
                    # Convert Series to DataFrame for feather compatibility
                    df = obj.to_frame()
                    df.to_feather(buffer, compression=self.compression)
                else:
                    obj.to_feather(buffer, compression=self.compression)

            elif self.format == "pickle":
                obj.to_pickle(buffer, compression=self.compression)

            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Pandas serialization failed with format {self.format}: {e}")
            raise SerializationError(f"Failed to serialize pandas object: {e}") from e

    def deserialize(self, data: bytes, expected_type: Type[T] | None = None) -> T:
        """Deserialize bytes to a pandas object.

        Args:
            data: The serialized data.
            expected_type: Optional expected type for validation.

        Returns:
            The deserialized pandas object.

        Raises:
            SerializationError: If deserialization fails.
        """
        try:
            buffer = BytesIO(data)

            if self.format == "parquet":
                obj = self.pd.read_parquet(buffer)

            elif self.format == "feather":
                obj = self.pd.read_feather(buffer)

            elif self.format == "pickle":
                obj = self.pd.read_pickle(buffer, compression=self.compression)

            # Type validation if expected_type is provided
            if expected_type is not None and not isinstance(obj, expected_type):
                logger.warning(
                    f"Type mismatch: expected {expected_type.__name__}, "
                    f"got {type(obj).__name__}"
                )
                raise SerializationError(
                    f"Type mismatch: expected {expected_type.__name__}, "
                    f"got {type(obj).__name__}"
                )

            return obj

        except Exception as e:
            logger.error(
                f"Pandas deserialization failed with format {self.format}: {e}"
            )
            raise SerializationError(f"Failed to deserialize pandas object: {e}") from e

    @property
    def is_binary(self) -> bool:
        """Return True if this serializer produces binary data."""
        return True

    @property
    def supports_streaming(self) -> bool:
        """Return True if this serializer supports streaming."""
        return self.format in ["parquet", "feather"]

    def get_metadata(self, obj: Any) -> dict[str, Any]:
        """Get metadata about the pandas object being serialized.

        Args:
            obj: The pandas object being serialized.

        Returns:
            A dictionary of metadata.
        """
        metadata = super().get_metadata(obj)

        if isinstance(obj, self.pd.DataFrame):
            metadata.update(
                {
                    "pandas_format": self.format,
                    "compression": self.compression,
                    "shape": obj.shape,
                    "columns": list(obj.columns),
                    "dtypes": {col: str(dtype) for col, dtype in obj.dtypes.items()},
                    "index_name": obj.index.name,
                    "memory_usage": obj.memory_usage(deep=True).sum(),
                }
            )
        elif isinstance(obj, self.pd.Series):
            metadata.update(
                {
                    "pandas_format": self.format,
                    "compression": self.compression,
                    "shape": obj.shape,
                    "dtype": str(obj.dtype),
                    "name": obj.name,
                    "index_name": obj.index.name,
                    "memory_usage": obj.memory_usage(deep=True),
                }
            )

        return metadata
