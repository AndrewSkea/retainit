"""MessagePack serializer implementation."""

import logging
from typing import Any, Type, TypeVar

from ..exceptions import SerializationError, UnsupportedDataTypeError
from .base import Serializer

logger = logging.getLogger(__name__)

T = TypeVar("T")

try:
    import msgpack

    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False
    msgpack = None


class MsgPackSerializer(Serializer):
    """MessagePack serializer for efficient binary serialization.

    This serializer provides efficient binary serialization for basic Python
    data types. It's more compact than JSON and handles binary data better.

    Requires the 'msgpack' package to be installed.
    """

    def __init__(self, use_bin_type: bool = True) -> None:
        """Initialize the MessagePack serializer.

        Args:
            use_bin_type: If True, use separate bin and str types.

        Raises:
            ImportError: If msgpack is not available.
        """
        if not MSGPACK_AVAILABLE:
            raise ImportError(
                "msgpack package is required for MsgPackSerializer. "
                "Install with: pip install msgpack"
            )

        self._use_bin_type = use_bin_type

    @property
    def name(self) -> str:
        """Return the name of this serializer."""
        return "msgpack"

    @property
    def content_type(self) -> str:
        """Return the MIME content type for this serializer."""
        return "application/msgpack"

    @property
    def is_binary(self) -> bool:
        """Return True if this serializer produces binary data."""
        return True

    def can_serialize(self, obj: Any) -> bool:
        """Check if this serializer can handle the given object.

        Args:
            obj: The object to check.

        Returns:
            True if this serializer can handle the object, False otherwise.
        """
        return self._is_msgpack_serializable(obj)

    def serialize(self, obj: Any) -> bytes:
        """Serialize an object to MessagePack bytes.

        Args:
            obj: The object to serialize.

        Returns:
            The serialized data as bytes.

        Raises:
            SerializationError: If serialization fails.
            UnsupportedDataTypeError: If the object type is not supported.
        """
        if not MSGPACK_AVAILABLE:
            raise SerializationError("msgpack package not available")

        if not self.can_serialize(obj):
            raise UnsupportedDataTypeError(
                f"Object of type {type(obj).__name__} is not MessagePack serializable",
                context={"object_type": type(obj).__name__},
            )

        try:
            return msgpack.packb(
                obj,
                use_bin_type=self._use_bin_type,
                strict_types=True,  # Prevent unsafe type conversions
            )

        except (TypeError, ValueError, OverflowError) as e:
            logger.error(f"MessagePack serialization failed: {e}")
            raise SerializationError(
                f"Failed to serialize object to MessagePack: {e}",
                context={"original_error": str(e), "object_type": type(obj).__name__},
            ) from e

    def deserialize(self, data: bytes, expected_type: Type[T] | None = None) -> T:
        """Deserialize MessagePack bytes to an object.

        Args:
            data: The serialized MessagePack data.
            expected_type: Optional expected type for validation.

        Returns:
            The deserialized object.

        Raises:
            SerializationError: If deserialization fails.
        """
        if not MSGPACK_AVAILABLE:
            raise SerializationError("msgpack package not available")

        try:
            obj = msgpack.unpackb(
                data,
                raw=False,  # Decode bytes to str
                strict_map_key=False,  # Allow non-string keys
                max_buffer_size=10 * 1024 * 1024,  # 10MB limit for safety
            )

            # Validate expected type if provided
            if expected_type is not None and not isinstance(obj, expected_type):
                raise SerializationError(
                    f"Deserialized object type {type(obj).__name__} "
                    f"does not match expected type {expected_type.__name__}",
                    context={
                        "actual_type": type(obj).__name__,
                        "expected_type": expected_type.__name__,
                    },
                )

            return obj

        except (
            msgpack.exceptions.ExtraData,
            msgpack.exceptions.InvalidData,
            msgpack.exceptions.ValueError,
        ) as e:
            logger.error(f"MessagePack deserialization failed: {e}")
            raise SerializationError(
                f"Failed to deserialize MessagePack data: {e}",
                context={"original_error": str(e)},
            ) from e

    def _is_msgpack_serializable(self, obj: Any) -> bool:
        """Check if an object is MessagePack serializable.

        Args:
            obj: The object to check.

        Returns:
            True if the object can be serialized to MessagePack safely.
        """
        if obj is None:
            return True

        if isinstance(obj, (str, int, float, bool, bytes)):
            return True

        if isinstance(obj, (list, tuple)):
            return all(self._is_msgpack_serializable(item) for item in obj)

        if isinstance(obj, dict):
            return all(
                self._is_msgpack_serializable(k) and self._is_msgpack_serializable(v)
                for k, v in obj.items()
            )

        return False
