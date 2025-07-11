"""Tests for validation utilities."""

import pytest

from retainit.exceptions import CacheKeyError, ValidationError
from retainit.validation import (
    sanitize_key_component,
    validate_backend_config,
    validate_cache_key,
    validate_function_args,
    validate_ttl,
    validate_value_size,
)


class TestCacheKeyValidation:
    """Test cache key validation."""

    def test_valid_keys(self):
        """Test valid cache keys."""
        valid_keys = [
            "simple_key",
            "key-with-dashes",
            "key.with.dots",
            "key:with:colons",
            "key123",
            "KEY_UPPERCASE",
            "a" * 250,  # Maximum length
        ]

        for key in valid_keys:
            validate_cache_key(key)  # Should not raise

    def test_invalid_key_types(self):
        """Test invalid key types."""
        invalid_keys = [
            123,
            None,
            [],
            {},
            object(),
        ]

        for key in invalid_keys:
            with pytest.raises(CacheKeyError, match="must be a string"):
                validate_cache_key(key)

    def test_empty_key(self):
        """Test empty key."""
        with pytest.raises(CacheKeyError, match="too short"):
            validate_cache_key("")

    def test_too_long_key(self):
        """Test key that's too long."""
        long_key = "a" * 251  # Over the limit
        with pytest.raises(CacheKeyError, match="too long"):
            validate_cache_key(long_key)

    def test_invalid_characters(self):
        """Test keys with invalid characters."""
        invalid_keys = [
            "key with spaces",
            "key/with/slashes",
            "key\\with\\backslashes",
            "key@with@symbols",
            "key#with#hash",
            "key$with$dollar",
        ]

        for key in invalid_keys:
            with pytest.raises(CacheKeyError, match="invalid characters"):
                validate_cache_key(key)

    def test_path_traversal_attempts(self):
        """Test keys with path traversal attempts."""
        dangerous_keys = [
            "../etc/passwd",
            "..\\windows\\system32",
            "key/../other",
            "key/./something",
        ]

        for key in dangerous_keys:
            with pytest.raises(CacheKeyError, match="dangerous path"):
                validate_cache_key(key)


class TestTTLValidation:
    """Test TTL validation."""

    def test_valid_ttl(self):
        """Test valid TTL values."""
        valid_ttls = [1, 60, 3600, 86400, 2147483647]

        for ttl in valid_ttls:
            validate_ttl(ttl)  # Should not raise

    def test_none_ttl(self):
        """Test None TTL (should be valid)."""
        validate_ttl(None)  # Should not raise

    def test_invalid_ttl_type(self):
        """Test invalid TTL types."""
        invalid_ttls = ["60", 3.14, [], {}]

        for ttl in invalid_ttls:
            with pytest.raises(ValidationError, match="must be an integer"):
                validate_ttl(ttl)

    def test_negative_ttl(self):
        """Test negative TTL."""
        with pytest.raises(ValidationError, match="at least 1"):
            validate_ttl(0)

        with pytest.raises(ValidationError, match="at least 1"):
            validate_ttl(-1)

    def test_too_large_ttl(self):
        """Test TTL that's too large."""
        with pytest.raises(ValidationError, match="cannot exceed"):
            validate_ttl(2147483648)  # Too large


class TestValueSizeValidation:
    """Test value size validation."""

    def test_small_values(self):
        """Test small values that should pass."""
        small_values = [
            "hello",
            42,
            [1, 2, 3],
            {"key": "value"},
        ]

        for value in small_values:
            validate_value_size(value)  # Should not raise

    def test_large_value(self):
        """Test value that's too large."""
        large_value = "x" * (2 * 1024 * 1024)  # 2MB

        with pytest.raises(ValidationError, match="too large to cache"):
            validate_value_size(large_value, max_size=1024 * 1024)  # 1MB limit

    def test_custom_size_limit(self):
        """Test custom size limit."""
        value = "x" * 1000

        # Should pass with high limit
        validate_value_size(value, max_size=2000)

        # Should fail with low limit
        with pytest.raises(ValidationError, match="too large"):
            validate_value_size(value, max_size=500)


class TestFunctionArgsValidation:
    """Test function arguments validation."""

    def test_simple_function(self):
        """Test validation of simple function arguments."""

        def simple_func(a, b, c=None):
            pass

        # Should not raise (just logs warnings for complex types)
        validate_function_args(simple_func, (1, "hello"), {"c": [1, 2, 3]})

    def test_complex_arguments(self):
        """Test validation with complex arguments."""

        def complex_func(obj):
            pass

        class CustomObject:
            pass

        # Should not raise (logs warning)
        validate_function_args(complex_func, (CustomObject(),), {})


class TestBackendConfigValidation:
    """Test backend configuration validation."""

    def test_valid_config(self):
        """Test valid configuration."""
        valid_configs = [
            {"ttl": 3600, "max_size": 1000},
            {"compression": True},
            {},  # Empty config
        ]

        for config in valid_configs:
            validate_backend_config(config)  # Should not raise

    def test_invalid_config_type(self):
        """Test invalid configuration type."""
        with pytest.raises(ValidationError, match="must be a dictionary"):
            validate_backend_config("not a dict")

    def test_invalid_ttl_in_config(self):
        """Test invalid TTL in configuration."""
        with pytest.raises(ValidationError, match="at least 1"):
            validate_backend_config({"ttl": 0})

    def test_invalid_max_size(self):
        """Test invalid max_size in configuration."""
        with pytest.raises(ValidationError, match="positive integer"):
            validate_backend_config({"max_size": -1})

        with pytest.raises(ValidationError, match="positive integer"):
            validate_backend_config({"max_size": "invalid"})


class TestKeySanitization:
    """Test key component sanitization."""

    def test_valid_components(self):
        """Test sanitization of valid components."""
        valid_components = [
            "simple",
            "with_underscores",
            "with-dashes",
            "with.dots",
            "with:colons",
        ]

        for component in valid_components:
            result = sanitize_key_component(component)
            assert result == component

    def test_invalid_characters(self):
        """Test sanitization of invalid characters."""
        test_cases = [
            ("hello world", "hello_world"),
            ("test@#$%", "test____"),
            ("a/b\\c", "a_b_c"),
            ("multiple   spaces", "multiple_spaces"),
            ("  leading_trailing  ", "leading_trailing"),
        ]

        for input_str, expected in test_cases:
            result = sanitize_key_component(input_str)
            assert result == expected

    def test_non_string_input(self):
        """Test sanitization with non-string input."""
        result = sanitize_key_component(123)
        assert result == "123"

        result = sanitize_key_component(None)
        assert result == "None"

    def test_too_short_component(self):
        """Test sanitization of too-short components."""
        result = sanitize_key_component("")
        assert result.startswith("key_")

        result = sanitize_key_component("_")
        assert result == "key"  # After stripping underscores

    def test_too_long_component(self):
        """Test sanitization of too-long components."""
        long_component = "a" * 300
        result = sanitize_key_component(long_component)
        assert len(result) <= 250
        assert result.endswith("_trunc")

    def test_multiple_underscores(self):
        """Test collapse of multiple underscores."""
        result = sanitize_key_component("test___multiple____underscores")
        assert result == "test_multiple_underscores"
