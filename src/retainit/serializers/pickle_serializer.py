"""Pickle serializer for general Python objects.

This serializer uses Python's pickle module for serialization, which can handle
most Python objects but comes with security risks when deserializing untrusted data.
"""

import logging
import pickle
from typing import Any, Type, TypeVar

from ..exceptions import SecurityError, SerializationError
from .base import Serializer

logger = logging.getLogger("retainit.serializers.pickle")

T = TypeVar("T")


class PickleSerializer(Serializer):
    """Pickle-based serializer for general Python objects.

    This serializer can handle most Python objects but should only be used
    with trusted data due to security risks in pickle deserialization.

    Attributes:
        protocol: Pickle protocol version to use.
        safe_mode: Whether to enable safety checks during deserialization.
    """

    def __init__(
        self, protocol: int = pickle.HIGHEST_PROTOCOL, safe_mode: bool = True
    ) -> None:
        """Initialize the pickle serializer.

        Args:
            protocol: Pickle protocol version to use.
            safe_mode: Whether to enable safety checks during deserialization.
        """
        self.protocol = protocol
        self.safe_mode = safe_mode

    @property
    def name(self) -> str:
        """Return the name of this serializer."""
        return "pickle"

    @property
    def content_type(self) -> str:
        """Return the MIME content type for this serializer."""
        return "application/python-pickle"

    def can_serialize(self, obj: Any) -> bool:
        """Check if this serializer can handle the given object.

        Args:
            obj: The object to check.

        Returns:
            True if this serializer can handle the object, False otherwise.
        """
        try:
            # Try a quick pickle test
            pickle.dumps(obj, protocol=self.protocol)
            return True
        except Exception:
            return False

    def serialize(self, obj: Any) -> bytes:
        """Serialize an object to bytes using pickle.

        Args:
            obj: The object to serialize.

        Returns:
            The serialized data as bytes.

        Raises:
            SerializationError: If serialization fails.
        """
        try:
            return pickle.dumps(obj, protocol=self.protocol)
        except Exception as e:
            logger.error(f"Pickle serialization failed: {e}")
            raise SerializationError(f"Failed to pickle object: {e}") from e

    def deserialize(self, data: bytes, expected_type: Type[T] | None = None) -> T:
        """Deserialize bytes to an object using pickle.

        Args:
            data: The serialized data.
            expected_type: Optional expected type for validation.

        Returns:
            The deserialized object.

        Raises:
            SerializationError: If deserialization fails.
            SecurityError: If the data appears malicious.
        """
        if self.safe_mode:
            # Basic safety check - look for potentially dangerous constructs
            if b"__reduce__" in data or b"__setstate__" in data:
                logger.warning("Potentially unsafe pickle data detected")
                raise SecurityError(
                    "Pickle data contains potentially unsafe constructs"
                )

        try:
            obj = pickle.loads(data)

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

        except (pickle.PickleError, EOFError, ValueError) as e:
            logger.error(f"Pickle deserialization failed: {e}")
            raise SerializationError(f"Failed to unpickle data: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error during pickle deserialization: {e}")
            raise SerializationError(f"Unexpected error during unpickling: {e}") from e

    @property
    def is_binary(self) -> bool:
        """Return True if this serializer produces binary data."""
        return True

    def get_metadata(self, obj: Any) -> dict[str, Any]:
        """Get metadata about the object being serialized.

        Args:
            obj: The object being serialized.

        Returns:
            A dictionary of metadata.
        """
        metadata = super().get_metadata(obj)
        metadata.update(
            {
                "pickle_protocol": self.protocol,
                "safe_mode": self.safe_mode,
            }
        )
        return metadata
