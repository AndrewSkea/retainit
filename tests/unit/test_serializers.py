"""Tests for serialization system."""

import pytest

from retainit.exceptions import SerializationError, UnsupportedDataTypeError
from retainit.serializers.base import Serializer
from retainit.serializers.json_serializer import JsonSerializer
from retainit.serializers.msgpack_serializer import MSGPACK_AVAILABLE, MsgPackSerializer
from retainit.serializers.registry import SerializerRegistry, get_registry


class TestSerializerInterface:
    """Test the base serializer interface."""

    def test_abstract_methods(self):
        """Test that Serializer is abstract."""
        with pytest.raises(TypeError):
            Serializer()  # Cannot instantiate abstract class


class TestJsonSerializer:
    """Test JSON serializer."""

    @pytest.fixture
    def serializer(self):
        """Create a JSON serializer."""
        return JsonSerializer()

    def test_properties(self, serializer):
        """Test serializer properties."""
        assert serializer.name == "json"
        assert serializer.content_type == "application/json"
        assert not serializer.is_binary

    def test_can_serialize_basic_types(self, serializer):
        """Test serialization support for basic types."""
        supported = [
            "string",
            42,
            3.14,
            True,
            False,
            None,
            [1, 2, 3],
            {"key": "value"},
            {"nested": {"list": [1, 2, 3]}},
        ]

        for value in supported:
            assert serializer.can_serialize(value)

    def test_cannot_serialize_complex_types(self, serializer):
        """Test that complex types are not supported."""

        class CustomClass:
            pass

        unsupported = [
            CustomClass(),
            lambda x: x,
            {"key": CustomClass()},
            [1, 2, CustomClass()],
        ]

        for value in unsupported:
            assert not serializer.can_serialize(value)

    def test_serialize_basic_types(self, serializer, sample_data):
        """Test serialization of basic types."""
        data = serializer.serialize(sample_data)
        assert isinstance(data, bytes)

        # Should be valid JSON
        import json

        parsed = json.loads(data.decode("utf-8"))
        assert isinstance(parsed, dict)

    def test_deserialize_basic_types(self, serializer, sample_data):
        """Test deserialization of basic types."""
        # Serialize then deserialize
        serialized = serializer.serialize(sample_data)
        deserialized = serializer.deserialize(serialized)

        # Note: tuples become lists in JSON
        expected = sample_data.copy()
        assert deserialized == expected

    def test_serialize_unsupported_type(self, serializer):
        """Test serialization of unsupported type."""

        class CustomClass:
            pass

        with pytest.raises(UnsupportedDataTypeError):
            serializer.serialize(CustomClass())

    def test_deserialize_invalid_json(self, serializer):
        """Test deserialization of invalid JSON."""
        with pytest.raises(SerializationError):
            serializer.deserialize(b"invalid json")

    def test_deserialize_invalid_utf8(self, serializer):
        """Test deserialization of invalid UTF-8."""
        with pytest.raises(SerializationError):
            serializer.deserialize(b"\\xff\\xfe")

    def test_type_validation_on_deserialize(self, serializer):
        """Test type validation during deserialization."""
        # Serialize a dict
        data = serializer.serialize({"key": "value"})

        # Deserialize expecting a list (should fail)
        with pytest.raises(SerializationError):
            serializer.deserialize(data, list)

    def test_tuple_to_list_conversion(self, serializer):
        """Test that tuples are converted to lists."""
        data = {"tuple": (1, 2, 3)}
        serialized = serializer.serialize(data)
        deserialized = serializer.deserialize(serialized)

        assert deserialized["tuple"] == [1, 2, 3]

    def test_custom_options(self):
        """Test custom serializer options."""
        serializer = JsonSerializer(ensure_ascii=True, indent=2)
        data = {"unicode": "café"}
        serialized = serializer.serialize(data)

        # Should be pretty-printed and ASCII-escaped
        json_str = serialized.decode("utf-8")
        assert "\\u00e9" in json_str  # é should be escaped
        assert "\n" in json_str  # Should be indented


@pytest.mark.skipif(not MSGPACK_AVAILABLE, reason="msgpack not available")
class TestMsgPackSerializer:
    """Test MessagePack serializer."""

    @pytest.fixture
    def serializer(self):
        """Create a MessagePack serializer."""
        return MsgPackSerializer()

    def test_properties(self, serializer):
        """Test serializer properties."""
        assert serializer.name == "msgpack"
        assert serializer.content_type == "application/msgpack"
        assert serializer.is_binary

    def test_can_serialize_basic_types(self, serializer):
        """Test serialization support for basic types."""
        supported = [
            "string",
            42,
            3.14,
            True,
            False,
            None,
            b"bytes",
            [1, 2, 3],
            {"key": "value"},
        ]

        for value in supported:
            assert serializer.can_serialize(value)

    def test_serialize_deserialize_roundtrip(self, serializer, sample_data):
        """Test serialize/deserialize roundtrip."""
        # Add bytes to sample data
        data = sample_data.copy()
        data["bytes"] = b"binary data"

        serialized = serializer.serialize(data)
        assert isinstance(serialized, bytes)

        deserialized = serializer.deserialize(serialized)
        assert deserialized == data

    def test_binary_data_support(self, serializer):
        """Test that binary data is supported."""
        data = {"binary": b"\\x00\\x01\\x02\\xff"}
        serialized = serializer.serialize(data)
        deserialized = serializer.deserialize(serialized)

        assert deserialized == data

    def test_unavailable_import_error(self):
        """Test import error when msgpack is not available."""
        # Mock the import error
        import retainit.serializers.msgpack_serializer as msgpack_module

        original_available = msgpack_module.MSGPACK_AVAILABLE

        try:
            msgpack_module.MSGPACK_AVAILABLE = False
            msgpack_module.msgpack = None

            with pytest.raises(ImportError, match="msgpack package is required"):
                MsgPackSerializer()
        finally:
            msgpack_module.MSGPACK_AVAILABLE = original_available


class TestSerializerRegistry:
    """Test serializer registry."""

    @pytest.fixture
    def registry(self):
        """Create a fresh serializer registry."""
        return SerializerRegistry()

    def test_builtin_serializers_registered(self, registry):
        """Test that builtin serializers are registered."""
        serializers = registry.list_serializers()
        assert "json" in serializers

        if MSGPACK_AVAILABLE:
            assert "msgpack" in serializers

    def test_get_serializer_by_name(self, registry):
        """Test getting serializer by name."""
        json_serializer = registry.get("json")
        assert isinstance(json_serializer, JsonSerializer)

    def test_get_nonexistent_serializer(self, registry):
        """Test getting nonexistent serializer."""
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    def test_register_custom_serializer(self, registry):
        """Test registering custom serializer."""

        class CustomSerializer(Serializer):
            @property
            def name(self):
                return "custom"

            @property
            def content_type(self):
                return "application/custom"

            def can_serialize(self, obj):
                return isinstance(obj, str)

            def serialize(self, obj):
                return obj.encode("utf-8")

            def deserialize(self, data, expected_type=None):
                return data.decode("utf-8")

            @property
            def is_binary(self):
                return True

        custom = CustomSerializer()
        registry.register(custom)

        assert "custom" in registry.list_serializers()
        assert registry.get("custom") is custom

    def test_register_duplicate_serializer(self, registry):
        """Test registering serializer with duplicate name."""
        custom1 = JsonSerializer()

        with pytest.raises(ValueError, match="already registered"):
            registry.register(custom1)

    def test_unregister_serializer(self, registry):
        """Test unregistering serializer."""

        # Register a custom serializer first
        class TestSerializer(JsonSerializer):
            @property
            def name(self):
                return "test"

        test_serializer = TestSerializer()
        registry.register(test_serializer)

        # Unregister it
        registry.unregister("test")

        assert "test" not in registry.list_serializers()
        with pytest.raises(KeyError):
            registry.get("test")

    def test_unregister_nonexistent_serializer(self, registry):
        """Test unregistering nonexistent serializer."""
        with pytest.raises(KeyError):
            registry.unregister("nonexistent")

    def test_find_best_serializer(self, registry, sample_data):
        """Test finding best serializer for data."""
        serializer = registry.find_best(sample_data)
        assert serializer.can_serialize(sample_data)

    def test_find_best_unsupported_data(self, registry):
        """Test finding serializer for unsupported data."""

        class CustomClass:
            pass

        with pytest.raises(UnsupportedDataTypeError):
            registry.find_best(CustomClass())

    def test_serialize_with_auto_selection(self, registry, sample_data):
        """Test serialization with automatic serializer selection."""
        data, serializer_name = registry.serialize(sample_data)
        assert isinstance(data, bytes)
        assert serializer_name in registry.list_serializers()

    def test_serialize_with_specific_serializer(self, registry, sample_data):
        """Test serialization with specific serializer."""
        data, serializer_name = registry.serialize(sample_data, "json")
        assert isinstance(data, bytes)
        assert serializer_name == "json"

    def test_deserialize_with_serializer_name(self, registry, sample_data):
        """Test deserialization with serializer name."""
        # Serialize first
        data, serializer_name = registry.serialize(sample_data, "json")

        # Deserialize
        result = registry.deserialize(data, serializer_name)
        assert result == sample_data

    def test_default_serializer(self, registry):
        """Test default serializer selection."""
        default = registry.get_default()
        assert default is not None

        # Default should be msgpack if available, otherwise json
        if MSGPACK_AVAILABLE:
            assert default.name == "msgpack"
        else:
            assert default.name == "json"

    def test_set_default_serializer(self, registry):
        """Test setting default serializer."""
        registry.set_default("json")
        default = registry.get_default()
        assert default.name == "json"

    def test_set_invalid_default_serializer(self, registry):
        """Test setting invalid default serializer."""
        with pytest.raises(KeyError):
            registry.set_default("nonexistent")


class TestGlobalRegistry:
    """Test global registry functions."""

    def test_get_global_registry(self):
        """Test getting global registry."""
        registry = get_registry()
        assert isinstance(registry, SerializerRegistry)

        # Should be the same instance
        registry2 = get_registry()
        assert registry is registry2

    def test_global_registry_has_builtins(self):
        """Test that global registry has builtin serializers."""
        registry = get_registry()
        serializers = registry.list_serializers()
        assert "json" in serializers
