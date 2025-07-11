"""JSON serializer implementation."""

import json
import logging
from typing import Any, Type, TypeVar

from ..exceptions import SerializationError, UnsupportedDataTypeError
from .base import Serializer

logger = logging.getLogger(__name__)

T = TypeVar("T")


class JsonSerializer(Serializer):
    """JSON serializer for basic Python data types.

    This serializer handles JSON-compatible types safely:
    - str, int, float, bool, None
    - list, tuple, dict
    - Nested combinations of the above

    It explicitly rejects complex objects to prevent security issues.
    """

    def __init__(self, ensure_ascii: bool = False, indent: int | None = None) -> None:
        """Initialize the JSON serializer.

        Args:
            ensure_ascii: If True, escape non-ASCII characters.
            indent: If specified, pretty-print with this indent level.
        """
        self._ensure_ascii = ensure_ascii
        self._indent = indent

    @property
    def name(self) -> str:
        """Return the name of this serializer."""
        return "json"

    @property
    def content_type(self) -> str:
        """Return the MIME content type for this serializer."""
        return "application/json"

    @property
    def is_binary(self) -> bool:
        """Return True if this serializer produces binary data."""
        return False

    def can_serialize(self, obj: Any) -> bool:
        """Check if this serializer can handle the given object.

        Args:
            obj: The object to check.

        Returns:
            True if this serializer can handle the object, False otherwise.
        """
        return self._is_json_serializable(obj)

    def serialize(self, obj: Any) -> bytes:
        """Serialize an object to JSON bytes.

        Args:
            obj: The object to serialize.

        Returns:
            The serialized data as UTF-8 encoded bytes.

        Raises:
            SerializationError: If serialization fails.
            UnsupportedDataTypeError: If the object type is not supported.
        """
        if not self.can_serialize(obj):
            raise UnsupportedDataTypeError(
                f"Object of type {type(obj).__name__} is not JSON serializable",
                context={"object_type": type(obj).__name__},
            )

        try:
            # Convert tuples to lists for JSON compatibility
            cleaned_obj = self._clean_for_json(obj)

            json_str = json.dumps(
                cleaned_obj,
                ensure_ascii=self._ensure_ascii,
                indent=self._indent,
                separators=(",", ":") if self._indent is None else None,
                sort_keys=True,  # For deterministic output
            )

            return json_str.encode("utf-8")

        except (TypeError, ValueError, OverflowError) as e:
            logger.error(f"JSON serialization failed: {e}")
            raise SerializationError(
                f"Failed to serialize object to JSON: {e}",
                context={"original_error": str(e), "object_type": type(obj).__name__},
            ) from e

    def deserialize(self, data: bytes, expected_type: Type[T] | None = None) -> T:
        """Deserialize JSON bytes to an object.

        Args:
            data: The serialized JSON data.
            expected_type: Optional expected type for validation.

        Returns:
            The deserialized object.

        Raises:
            SerializationError: If deserialization fails.
        """
        try:
            json_str = data.decode("utf-8")
            obj = json.loads(json_str)

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

        except UnicodeDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            raise SerializationError(
                f"Failed to decode JSON data: {e}", context={"original_error": str(e)}
            ) from e

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            raise SerializationError(
                f"Failed to parse JSON data: {e}", context={"original_error": str(e)}
            ) from e

    def _is_json_serializable(self, obj: Any) -> bool:
        """Check if an object is JSON serializable.

        Args:
            obj: The object to check.

        Returns:
            True if the object can be serialized to JSON safely.
        """
        if obj is None:
            return True

        if isinstance(obj, (str, int, float, bool)):
            return True

        if isinstance(obj, (list, tuple)):
            return all(self._is_json_serializable(item) for item in obj)

        if isinstance(obj, dict):
            return all(isinstance(k, str) for k in obj.keys()) and all(
                self._is_json_serializable(v) for v in obj.values()
            )

        return False

    def _clean_for_json(self, obj: Any) -> Any:
        """Clean an object for JSON serialization.

        This converts tuples to lists and ensures all data is JSON compatible.

        Args:
            obj: The object to clean.

        Returns:
            A JSON-compatible version of the object.
        """
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj

        if isinstance(obj, tuple):
            return [self._clean_for_json(item) for item in obj]

        if isinstance(obj, list):
            return [self._clean_for_json(item) for item in obj]

        if isinstance(obj, dict):
            return {str(k): self._clean_for_json(v) for k, v in obj.items()}

        # This should not happen if can_serialize was called first
        raise UnsupportedDataTypeError(
            f"Cannot clean object of type {type(obj).__name__} for JSON"
        )
