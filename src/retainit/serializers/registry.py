"""Serializer registry for managing available serializers."""

import logging
from typing import Any, Type

from ..exceptions import SerializationError, UnsupportedDataTypeError
from .base import Serializer
from .json_serializer import JsonSerializer
from .msgpack_serializer import MSGPACK_AVAILABLE, MsgPackSerializer

logger = logging.getLogger(__name__)


class SerializerRegistry:
    """Registry for managing serializers.

    This class maintains a registry of available serializers and provides
    methods to find the best serializer for a given object.
    """

    def __init__(self) -> None:
        """Initialize the serializer registry."""
        self._serializers: dict[str, Serializer] = {}
        self._auto_serializers: list[Serializer] = []
        self._default_serializer_name = "json"

        # Register built-in serializers
        self._register_builtin_serializers()

    def _register_builtin_serializers(self) -> None:
        """Register built-in serializers."""
        # Always register JSON serializer
        json_serializer = JsonSerializer()
        self.register(json_serializer)
        self._auto_serializers.append(json_serializer)

        # Register MessagePack if available
        if MSGPACK_AVAILABLE:
            msgpack_serializer = MsgPackSerializer()
            self.register(msgpack_serializer)
            self._auto_serializers.append(msgpack_serializer)
            # Prefer msgpack for efficiency if available
            self._default_serializer_name = "msgpack"

        # Register specialized serializers if their dependencies are available
        self._register_specialized_serializers()

    def _register_specialized_serializers(self) -> None:
        """Register specialized serializers based on available dependencies."""
        # Register pickle serializer (always available)
        try:
            from .pickle_serializer import PickleSerializer

            pickle_serializer = PickleSerializer()
            self.register(pickle_serializer)
            self._auto_serializers.append(pickle_serializer)
        except ImportError:
            logger.debug("Pickle serializer not available")

        # Register pandas serializer if available
        try:
            from .pandas_serializer import PandasSerializer

            pandas_serializer = PandasSerializer()
            self.register(pandas_serializer)
            # Insert before general serializers for priority
            self._auto_serializers.insert(0, pandas_serializer)
        except Exception:
            logger.debug("Pandas serializer not available")

        # Register numpy serializer if available
        try:
            from .numpy_serializer import NumpySerializer

            numpy_serializer = NumpySerializer()
            self.register(numpy_serializer)
            # Insert before general serializers for priority
            self._auto_serializers.insert(0, numpy_serializer)
        except Exception:
            logger.debug("NumPy serializer not available")

    def register(self, serializer: Serializer) -> None:
        """Register a serializer.

        Args:
            serializer: The serializer to register.

        Raises:
            ValueError: If a serializer with the same name is already registered.
        """
        if serializer.name in self._serializers:
            raise ValueError(f"Serializer '{serializer.name}' is already registered")

        self._serializers[serializer.name] = serializer
        logger.debug(f"Registered serializer: {serializer.name}")

    def unregister(self, name: str) -> None:
        """Unregister a serializer.

        Args:
            name: The name of the serializer to unregister.

        Raises:
            KeyError: If no serializer with the given name is registered.
        """
        if name not in self._serializers:
            raise KeyError(f"No serializer named '{name}' is registered")

        serializer = self._serializers.pop(name)

        # Remove from auto serializers if present
        self._auto_serializers = [s for s in self._auto_serializers if s.name != name]

        logger.debug(f"Unregistered serializer: {name}")

    def get(self, name: str) -> Serializer:
        """Get a serializer by name.

        Args:
            name: The name of the serializer.

        Returns:
            The serializer instance.

        Raises:
            KeyError: If no serializer with the given name is registered.
        """
        if name not in self._serializers:
            raise KeyError(f"No serializer named '{name}' is registered")

        return self._serializers[name]

    def get_default(self) -> Serializer:
        """Get the default serializer.

        Returns:
            The default serializer instance.
        """
        return self.get(self._default_serializer_name)

    def set_default(self, name: str) -> None:
        """Set the default serializer.

        Args:
            name: The name of the serializer to set as default.

        Raises:
            KeyError: If no serializer with the given name is registered.
        """
        if name not in self._serializers:
            raise KeyError(f"No serializer named '{name}' is registered")

        self._default_serializer_name = name
        logger.debug(f"Set default serializer to: {name}")

    def find_best(self, obj: Any) -> Serializer:
        """Find the best serializer for an object.

        This method tries to find the most appropriate serializer for the
        given object by checking which serializers can handle it.

        Args:
            obj: The object to find a serializer for.

        Returns:
            The best serializer for the object.

        Raises:
            UnsupportedDataTypeError: If no serializer can handle the object.
        """
        # Try auto serializers in order of preference
        for serializer in self._auto_serializers:
            if serializer.can_serialize(obj):
                logger.debug(
                    f"Selected serializer '{serializer.name}' for {type(obj).__name__}"
                )
                return serializer

        # If no auto serializer works, raise an error
        raise UnsupportedDataTypeError(
            f"No suitable serializer found for object of type {type(obj).__name__}",
            context={
                "object_type": type(obj).__name__,
                "available_serializers": list(self._serializers.keys()),
            },
        )

    def list_serializers(self) -> list[str]:
        """List all registered serializer names.

        Returns:
            A list of registered serializer names.
        """
        return list(self._serializers.keys())

    def serialize(
        self, obj: Any, serializer_name: str | None = None
    ) -> tuple[bytes, str]:
        """Serialize an object using the specified or best serializer.

        Args:
            obj: The object to serialize.
            serializer_name: Optional serializer name. If None, finds the best one.

        Returns:
            A tuple of (serialized_data, serializer_name_used).

        Raises:
            SerializationError: If serialization fails.
            UnsupportedDataTypeError: If no suitable serializer is found.
        """
        if serializer_name is not None:
            serializer = self.get(serializer_name)
        else:
            serializer = self.find_best(obj)

        data = serializer.serialize(obj)
        return data, serializer.name

    def deserialize(
        self, data: bytes, serializer_name: str, expected_type: Type | None = None
    ) -> Any:
        """Deserialize data using the specified serializer.

        Args:
            data: The serialized data.
            serializer_name: The name of the serializer to use.
            expected_type: Optional expected type for validation.

        Returns:
            The deserialized object.

        Raises:
            SerializationError: If deserialization fails.
            KeyError: If the serializer is not found.
        """
        serializer = self.get(serializer_name)
        return serializer.deserialize(data, expected_type)


# Global registry instance
_registry = SerializerRegistry()


def get_serializer(name: str) -> Serializer:
    """Get a serializer by name from the global registry.

    Args:
        name: The name of the serializer.

    Returns:
        The serializer instance.
    """
    return _registry.get(name)


def register_serializer(serializer: Serializer) -> None:
    """Register a serializer in the global registry.

    Args:
        serializer: The serializer to register.
    """
    _registry.register(serializer)


def get_registry() -> SerializerRegistry:
    """Get the global serializer registry.

    Returns:
        The global registry instance.
    """
    return _registry
