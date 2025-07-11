"""Base serializer interface."""

import abc
from typing import Any, Type, TypeVar

T = TypeVar("T")


class Serializer(abc.ABC):
    """Abstract base class for serializers.

    All serializers must implement this interface to provide consistent
    serialization and deserialization capabilities.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Return the name of this serializer."""

    @property
    @abc.abstractmethod
    def content_type(self) -> str:
        """Return the MIME content type for this serializer."""

    @abc.abstractmethod
    def can_serialize(self, obj: Any) -> bool:
        """Check if this serializer can handle the given object.

        Args:
            obj: The object to check.

        Returns:
            True if this serializer can handle the object, False otherwise.
        """

    @abc.abstractmethod
    def serialize(self, obj: Any) -> bytes:
        """Serialize an object to bytes.

        Args:
            obj: The object to serialize.

        Returns:
            The serialized data as bytes.

        Raises:
            SerializationError: If serialization fails.
        """

    @abc.abstractmethod
    def deserialize(self, data: bytes, expected_type: Type[T] | None = None) -> T:
        """Deserialize bytes to an object.

        Args:
            data: The serialized data.
            expected_type: Optional expected type for validation.

        Returns:
            The deserialized object.

        Raises:
            SerializationError: If deserialization fails.
            SecurityError: If the data appears malicious.
        """

    @property
    @abc.abstractmethod
    def is_binary(self) -> bool:
        """Return True if this serializer produces binary data."""

    @property
    def supports_streaming(self) -> bool:
        """Return True if this serializer supports streaming.

        Override this in subclasses that support streaming serialization.
        """
        return False

    def get_metadata(self, obj: Any) -> dict[str, Any]:
        """Get metadata about the object being serialized.

        This can be used to store type information or other metadata
        alongside the serialized data.

        Args:
            obj: The object being serialized.

        Returns:
            A dictionary of metadata.
        """
        return {
            "type": type(obj).__name__,
            "module": type(obj).__module__,
        }
