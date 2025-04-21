"""Configuration system for retainit.

This module provides a flexible configuration system that can load settings from
multiple sources including environment variables, config files (JSON, YAML, TOML),
.env files, and programmatic configuration.

The configuration is loaded with a specific precedence order:
1. Programmatic configuration (highest precedence)
2. Environment variables with RETAINIT_ prefix
3. Config files (.retainit.json, .retainit.yaml, pyproject.toml)
4. .env files
5. Default values (lowest precedence)
"""

import json
import logging
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TypeVar, Union, cast

# Setup logging
logger = logging.getLogger("retainit.config")

# Define types
ConfigValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
ConfigDict = Dict[str, ConfigValue]
T = TypeVar("T")


class CacheBackendType(str, Enum):
    """Supported cache backend types."""

    MEMORY = "memory"
    DISK = "disk"
    REDIS = "redis"
    S3 = "s3"
    DYNAMODB = "dynamodb"
    TIERED = "tiered"  # Uses multiple backends with fallback


class ConfigSource(str, Enum):
    """Possible sources of configuration values."""

    DEFAULT = "default"
    ENV_FILE = "env_file"
    ENV_VAR = "environment_variable"
    CONFIG_FILE = "config_file"
    PROGRAMMATIC = "programmatic"


class ConfigError(Exception):
    """Base exception for configuration errors."""

    pass


class ConfigFileNotFound(ConfigError):
    """Raised when a specified config file is not found."""

    pass


class ConfigFileParseError(ConfigError):
    """Raised when a config file cannot be parsed."""

    pass


class Config:
    """Main configuration class for retainit.

    This class manages the configuration for the retainit caching library,
    supporting multiple sources of configuration with a defined precedence order.

    Attributes:
        _config: Dictionary containing the current configuration values.
        _sources: Dictionary tracking where each config value came from.
    """

    # Default configuration values
    _defaults: ConfigDict = {
        "backend": CacheBackendType.MEMORY.value,
        "ttl": 3600,  # Default TTL of 1 hour
        "base_path": ".cache/function_resp",
        "compression": False,
        "key_prefix": "retainit",
        "max_size": None,  # For memory cache
        "redis_url": "redis://localhost:6379",
        "redis_password": None,
        "redis_ssl": False,
        "redis_cert_reqs": None,
        "redis_ca_certs": None,
        "s3_bucket": None,
        "s3_prefix": "retainit",
        "s3_region": None,
        "dynamodb_table": None,
        "dynamodb_region": None,
        "enable_metrics": False,
        "metrics_backend": None,
        "metrics_namespace": "retainit",
        "log_level": "WARNING",
        "encryption": False,
        "encryption_key": None,
        "circuit_breaker": False,
        "circuit_breaker_threshold": 5,
        "circuit_breaker_timeout": 60,
    }

    def __init__(self) -> None:
        """Initialize a new Config instance with default values."""
        self._config: ConfigDict = self._defaults.copy()
        self._sources: Dict[str, ConfigSource] = {
            k: ConfigSource.DEFAULT for k in self._defaults
        }
        self._initialized: bool = False

    def init(
        self,
        config_file: Optional[str] = None,
        env_file: Optional[str] = None,
        profile: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the configuration from all sources.

        Args:
            config_file: Optional path to a config file to load.
            env_file: Optional path to a .env file to load.
            profile: Optional profile name to use.
            **kwargs: Additional configuration values to set programmatically.
        """
        if self._initialized:
            logger.warning("Configuration already initialized, re-initializing")

        # Load configuration in order of precedence (lowest to highest)
        # 1. Start with defaults (already loaded in __init__)
        # 2. Load from .env file if specified
        if env_file:
            self._load_env_file(env_file)

        # 3. Load from config file if specified or search for default config files
        if config_file:
            self._load_config_file(config_file)
        else:
            self._load_default_config_files()

        # 4. Load from environment variables
        self._load_from_env()

        # 5. Apply profile if specified
        if profile:
            self._apply_profile(profile)

        # 6. Apply programmatic configuration (highest precedence)
        if kwargs:
            self._update_from_dict(kwargs, ConfigSource.PROGRAMMATIC)

        # Validate the configuration
        self._validate()

        # Set up the logger with the configured log level
        self._setup_logging()

        self._initialized = True
        logger.debug(f"Configuration initialized with backend: {self.get('backend')}")

    def _load_env_file(self, env_file_path: str) -> None:
        """Load configuration from a .env file.

        Args:
            env_file_path: Path to the .env file to load.

        Raises:
            ConfigFileNotFound: If the specified .env file is not found.
            ConfigFileParseError: If the .env file cannot be parsed.
        """
        env_path = Path(env_file_path)
        if not env_path.exists():
            raise ConfigFileNotFound(f".env file not found: {env_file_path}")

        try:
            # Import dotenv here to avoid making it a required dependency
            try:
                from dotenv import load_dotenv
            except ImportError:
                logger.warning(
                    "python-dotenv package not installed, cannot load .env file"
                )
                return

            # Load the .env file
            load_dotenv(env_path)

            # Now that variables are loaded into environment, load them from there
            self._load_from_env()
            logger.debug(f"Loaded configuration from .env file: {env_file_path}")
        except Exception as e:
            raise ConfigFileParseError(f"Error parsing .env file: {e}")

    def _load_config_file(self, config_file_path: str) -> None:
        """Load configuration from a specified config file.

        Args:
            config_file_path: Path to the config file to load.

        Raises:
            ConfigFileNotFound: If the specified config file is not found.
            ConfigFileParseError: If the config file cannot be parsed.
        """
        file_path = Path(config_file_path)
        if not file_path.exists():
            raise ConfigFileNotFound(f"Config file not found: {config_file_path}")

        try:
            suffix = file_path.suffix.lower()
            config_data: ConfigDict = {}

            if suffix == ".json":
                with open(file_path, "r") as f:
                    config_data = json.load(f)
            elif suffix in (".yaml", ".yml"):
                try:
                    import yaml

                    with open(file_path, "r") as f:
                        config_data = yaml.safe_load(f)
                except ImportError:
                    logger.warning(
                        "PyYAML package not installed, cannot load YAML config file"
                    )
                    return
            elif suffix == ".toml":
                try:
                    import tomli

                    with open(file_path, "rb") as f:
                        toml_data = tomli.load(f)
                        # Look for config under [tool.retainit] or [retainit] sections
                        if "tool" in toml_data and "retainit" in toml_data["tool"]:
                            config_data = toml_data["tool"]["retainit"]
                        elif "retainit" in toml_data:
                            config_data = toml_data["retainit"]
                except ImportError:
                    logger.warning(
                        "tomli package not installed, cannot load TOML config file"
                    )
                    return
            else:
                raise ConfigFileParseError(
                    f"Unsupported config file format: {suffix} (supported: .json, .yaml, .yml, .toml)"
                )

            # Handle the case where config might be nested under a 'retainit' key
            if "retainit" in config_data:
                config_data = config_data["retainit"]

            # Update the configuration
            self._update_from_dict(config_data, ConfigSource.CONFIG_FILE)
            logger.debug(f"Loaded configuration from file: {config_file_path}")
        except Exception as e:
            raise ConfigFileParseError(f"Error parsing config file: {e}")

    def _load_default_config_files(self) -> None:
        """Search for and load configuration from default config files.

        This method checks for config files in the following locations and order:
        1. pyproject.toml (looking for [tool.retainit] section)
        2. .retainit.toml
        3. .retainit.yaml or .retainit.yml
        4. .retainit.json
        5. retainit.toml
        6. retainit.yaml or retainit.yml
        7. retainit.json
        """
        # Define the search paths
        search_paths = [
            # Current directory
            Path.cwd(),
            # User's home directory
            Path.home(),
        ]

        # Define the file patterns to search for
        file_patterns = [
            "pyproject.toml",
            ".retainit.toml",
            ".retainit.yaml",
            ".retainit.yml",
            ".retainit.json",
            "retainit.toml",
            "retainit.yaml",
            "retainit.yml",
            "retainit.json",
        ]

        # Search for and load the first config file found
        for path in search_paths:
            for pattern in file_patterns:
                config_path = path / pattern
                if config_path.exists():
                    try:
                        self._load_config_file(str(config_path))
                        # Once we've loaded a config file, return (don't load multiple files)
                        return
                    except ConfigError as e:
                        logger.warning(f"Error loading config file {config_path}: {e}")

    def _load_from_env(self) -> None:
        """Load configuration from environment variables with RETAINIT_ prefix.

        This method looks for environment variables with the RETAINIT_ prefix
        and updates the configuration accordingly. It handles type conversion for
        known config keys.
        """
        boolean_keys = {
            "compression",
            "enable_metrics",
            "redis_ssl",
            "encryption",
            "circuit_breaker",
        }
        int_keys = {"ttl", "max_size", "circuit_breaker_threshold", "circuit_breaker_timeout"}
        float_keys = set()  # For potential future float config options

        # Get all environment variables with RETAINIT_ prefix
        prefix = "RETAINIT_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix) :].lower()

                # Skip if this isn't a known config key
                if config_key not in self._defaults:
                    continue

                # Convert value to the appropriate type
                typed_value: ConfigValue
                if config_key in boolean_keys:
                    typed_value = value.lower() in ("true", "1", "yes", "y", "on")
                elif config_key in int_keys:
                    try:
                        typed_value = int(value)
                    except ValueError:
                        logger.warning(
                            f"Invalid integer value for {key}: {value}, ignoring"
                        )
                        continue
                elif config_key in float_keys:
                    try:
                        typed_value = float(value)
                    except ValueError:
                        logger.warning(
                            f"Invalid float value for {key}: {value}, ignoring"
                        )
                        continue
                elif value.lower() == "none":
                    typed_value = None
                else:
                    typed_value = value

                # Update the configuration
                self._config[config_key] = typed_value
                self._sources[config_key] = ConfigSource.ENV_VAR
                logger.debug(f"Loaded {config_key}={typed_value} from environment")

    def _apply_profile(self, profile_name: str) -> None:
        """Apply a named profile configuration.

        Args:
            profile_name: The name of the profile to apply.

        Raises:
            ValueError: If the profile does not exist in the configuration.
        """
        # Check if profiles are defined in the config
        profiles = self._config.get("profiles")
        if not profiles or not isinstance(profiles, dict):
            raise ValueError(f"Profile '{profile_name}' not found in configuration")

        # Check if the requested profile exists
        profile = profiles.get(profile_name)
        if not profile or not isinstance(profile, dict):
            raise ValueError(f"Profile '{profile_name}' not found in configuration")

        # Apply the profile settings
        self._update_from_dict(cast(ConfigDict, profile), ConfigSource.CONFIG_FILE)
        logger.debug(f"Applied profile: {profile_name}")

    def _update_from_dict(self, config_dict: Dict[str, Any], source: ConfigSource) -> None:
        """Update the configuration from a dictionary.

        Args:
            config_dict: Dictionary containing configuration values.
            source: The source of the configuration values.
        """
        for key, value in config_dict.items():
            # Skip unknown keys
            if key not in self._defaults and key != "profiles":
                logger.warning(f"Unknown configuration key: {key}")
                continue

            # Allow nested backend-specific configuration
            if isinstance(value, dict) and key in ("redis", "s3", "dynamodb", "metrics"):
                for sub_key, sub_value in value.items():
                    full_key = f"{key}_{sub_key}"
                    if full_key in self._defaults:
                        self._config[full_key] = sub_value
                        self._sources[full_key] = source
            else:
                # Handle environment variable expansion for string values
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]
                    env_value = os.environ.get(env_var)
                    if env_value is not None:
                        value = env_value
                    else:
                        logger.warning(
                            f"Environment variable {env_var} referenced in config not found"
                        )

                # Store the config value and its source
                self._config[key] = value
                self._sources[key] = source

    def _validate(self) -> None:
        """Validate the configuration.

        This method checks for required values and ensures the configuration is consistent.

        Raises:
            ValueError: If the configuration is invalid.
        """
        # Validate backend
        backend = self._config.get("backend")
        if backend not in [e.value for e in CacheBackendType]:
            raise ValueError(f"Invalid backend: {backend}")

        # Validate backend-specific requirements
        if backend == CacheBackendType.REDIS.value:
            if not self._config.get("redis_url"):
                raise ValueError("Redis URL must be specified when using Redis backend")
        elif backend == CacheBackendType.S3.value:
            if not self._config.get("s3_bucket"):
                raise ValueError("S3 bucket must be specified when using S3 backend")
        elif backend == CacheBackendType.DYNAMODB.value:
            if not self._config.get("dynamodb_table"):
                raise ValueError(
                    "DynamoDB table must be specified when using DynamoDB backend"
                )

        # Validate metrics configuration
        if self._config.get("enable_metrics") and not self._config.get("metrics_backend"):
            raise ValueError(
                "Metrics backend must be specified when metrics are enabled"
            )

        # Validate encryption configuration
        if self._config.get("encryption") and not self._config.get("encryption_key"):
            raise ValueError("Encryption key must be specified when encryption is enabled")

    def _setup_logging(self) -> None:
        """Configure the logger based on the log_level setting."""
        log_level_str = str(self._config.get("log_level", "WARNING")).upper()
        log_level = getattr(logging, log_level_str, logging.WARNING)
        
        # Configure the retainit logger
        logger.setLevel(log_level)
        
        # If no handlers are configured, add a default handler
        if not logger.handlers and not logging.root.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

    def get(self, key: str, default: Optional[T] = None) -> Union[ConfigValue, T]:
        """Get a configuration value by key.

        Args:
            key: The configuration key to get.
            default: The default value to return if the key is not found.

        Returns:
            The configuration value, or the default if the key is not found.
        """
        return self._config.get(key, default)

    def get_all(self) -> ConfigDict:
        """Get all configuration values.

        Returns:
            A dictionary containing all configuration values.
        """
        return self._config.copy()

    def get_source(self, key: str) -> Optional[ConfigSource]:
        """Get the source of a configuration value.

        Args:
            key: The configuration key to get the source for.

        Returns:
            The source of the configuration value, or None if the key is not found.
        """
        return self._sources.get(key)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value.

        Args:
            key: The configuration key to set.
            value: The value to set.

        Raises:
            ValueError: If the key is not a known configuration option.
        """
        if key not in self._defaults and key != "profiles":
            raise ValueError(f"Unknown configuration key: {key}")

        self._config[key] = value
        self._sources[key] = ConfigSource.PROGRAMMATIC
        
        # If changing backend or related settings, re-validate
        if key in ("backend", "redis_url", "s3_bucket", "dynamodb_table"):
            self._validate()

    def is_initialized(self) -> bool:
        """Check if the configuration has been initialized.

        Returns:
            True if the configuration has been initialized, False otherwise.
        """
        return self._initialized


# Create a singleton instance
config = Config()