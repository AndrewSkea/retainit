"""NumPy serializer for array objects.

This serializer provides efficient serialization for NumPy arrays using
the native .npy format with optional compression.
"""

import logging
from io import BytesIO
from typing import Any, Type, TypeVar

from ..exceptions import BackendNotAvailableError, SerializationError
from .base import Serializer

logger = logging.getLogger("retainit.serializers.numpy")

T = TypeVar("T")


class NumpySerializer(Serializer):
    """NumPy-specific serializer for array objects.

    This serializer can handle NumPy arrays using the efficient .npy format
    with optional compression for better storage efficiency.

    Attributes:
        compressed: Whether to use compressed format.
    """

    def __init__(self, compressed: bool = True) -> None:
        """Initialize the NumPy serializer.

        Args:
            compressed: Whether to use compressed format (.npz).

        Raises:
            BackendNotAvailableError: If numpy is not available.
        """
        try:
            import numpy as np

            self.np = np
        except ImportError as e:
            raise BackendNotAvailableError(
                "NumPy serializer requires 'numpy' package. "
                "Install with 'pip install retainit[numpy]'",
                context={"import_error": str(e)},
            ) from e

        self.compressed = compressed

    @property
    def name(self) -> str:
        """Return the name of this serializer."""
        return "numpy_compressed" if self.compressed else "numpy"

    @property
    def content_type(self) -> str:
        """Return the MIME content type for this serializer."""
        return (
            "application/numpy"
            if not self.compressed
            else "application/numpy-compressed"
        )

    def can_serialize(self, obj: Any) -> bool:
        """Check if this serializer can handle the given object.

        Args:
            obj: The object to check.

        Returns:
            True if this serializer can handle the object, False otherwise.
        """
        return isinstance(obj, self.np.ndarray)

    def serialize(self, obj: Any) -> bytes:
        """Serialize a NumPy array to bytes.

        Args:
            obj: The NumPy array to serialize.

        Returns:
            The serialized data as bytes.

        Raises:
            SerializationError: If serialization fails.
        """
        if not self.can_serialize(obj):
            raise SerializationError(
                f"Object of type {type(obj).__name__} cannot be serialized by numpy serializer"
            )

        try:
            buffer = BytesIO()

            if self.compressed:
                # Use savez_compressed for better compression
                self.np.savez_compressed(buffer, array=obj)
            else:
                # Use save for faster but larger files
                self.np.save(buffer, obj)

            return buffer.getvalue()

        except Exception as e:
            logger.error(f"NumPy serialization failed: {e}")
            raise SerializationError(f"Failed to serialize numpy array: {e}") from e

    def deserialize(self, data: bytes, expected_type: Type[T] | None = None) -> T:
        """Deserialize bytes to a NumPy array.

        Args:
            data: The serialized data.
            expected_type: Optional expected type for validation.

        Returns:
            The deserialized NumPy array.

        Raises:
            SerializationError: If deserialization fails.
        """
        try:
            buffer = BytesIO(data)

            if self.compressed:
                # Load from compressed format
                loaded = self.np.load(buffer)
                if isinstance(loaded, self.np.lib.npyio.NpzFile):
                    # Extract the array from the npz file
                    obj = loaded["array"]
                else:
                    obj = loaded
            else:
                # Load from uncompressed format
                obj = self.np.load(buffer)

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
            logger.error(f"NumPy deserialization failed: {e}")
            raise SerializationError(f"Failed to deserialize numpy array: {e}") from e

    @property
    def is_binary(self) -> bool:
        """Return True if this serializer produces binary data."""
        return True

    @property
    def supports_streaming(self) -> bool:
        """Return True if this serializer supports streaming."""
        return False  # NumPy arrays are typically loaded entirely into memory

    def get_metadata(self, obj: Any) -> dict[str, Any]:
        """Get metadata about the NumPy array being serialized.

        Args:
            obj: The NumPy array being serialized.

        Returns:
            A dictionary of metadata.
        """
        metadata = super().get_metadata(obj)

        if isinstance(obj, self.np.ndarray):
            metadata.update(
                {
                    "numpy_compressed": self.compressed,
                    "shape": obj.shape,
                    "dtype": str(obj.dtype),
                    "size": obj.size,
                    "ndim": obj.ndim,
                    "itemsize": obj.itemsize,
                    "memory_usage": obj.nbytes,
                    "fortran_order": obj.flags.f_contiguous,
                }
            )

        return metadata
