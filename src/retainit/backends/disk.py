"""Disk cache backend implementation.

This module provides a file-system based cache backend that stores cached values
in files on disk using safe serialization.
"""

import asyncio
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional, TypeVar

from ..backends.base import CacheBackend
from ..exceptions import BackendError, CorruptedDataError, ValidationError
from ..serializers.registry import get_registry
from ..validation import (
    sanitize_key_component,
    validate_cache_key,
    validate_ttl,
    validate_value_size,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Compression module availability
try:
    import zlib

    COMPRESSION_AVAILABLE = True
except ImportError:
    COMPRESSION_AVAILABLE = False
    zlib = None


class DiskCache(CacheBackend[T]):
    """File-system based cache backend.

    This cache stores values in files on disk, with optional compression.

    Attributes:
        base_directory: Base directory where cache files are stored.
        compression: Whether to compress cached values.
        file_locks: Dictionary of locks for each file to ensure process-safety.
    """

    def __init__(
        self,
        base_directory: str = ".cache/retainit",
        compression: bool = False,
        max_value_size: int = 10 * 1024 * 1024,  # 10MB
    ):
        """Initialize the disk cache.

        Args:
            base_directory: Base directory where cache files are stored.
            compression: Whether to compress cached values.
            max_value_size: Maximum size of individual values in bytes.

        Raises:
            ValidationError: If base_directory is invalid.
            BackendError: If directory creation fails.
        """
        if not base_directory or not isinstance(base_directory, str):
            raise ValidationError(
                "base_directory must be a non-empty string",
                context={"base_directory": base_directory},
            )

        self.base_directory = Path(base_directory).resolve()
        self.compression = compression
        self.max_value_size = max_value_size
        self.file_locks = {}  # Lock per file
        self.global_lock = asyncio.Lock()  # For operations on the file_locks dict
        self._serializer_registry = get_registry()

        # Statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "corrupted_files": 0,
        }

        # Create base directory if it doesn't exist
        try:
            self.base_directory.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise BackendError(
                f"Failed to create cache directory {self.base_directory}: {e}",
                context={"directory": str(self.base_directory), "error": str(e)},
            ) from e

    def _key_to_path(self, key: str) -> Path:
        """Convert a cache key to a file path.

        To avoid having too many files in one directory, we use the first two
        characters of the key's hash as a subdirectory.

        Args:
            key: The cache key.

        Returns:
            The file path for the cache key.

        Raises:
            BackendError: If directory creation fails.
        """
        # Use SHA-256 instead of MD5 for better security
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()

        # Create subdirectory based on hash prefix
        subdir = self.base_directory / key_hash[:2]
        try:
            subdir.mkdir(exist_ok=True)
        except OSError as e:
            raise BackendError(
                f"Failed to create cache subdirectory {subdir}: {e}",
                context={"subdir": str(subdir), "error": str(e)},
            ) from e

        return subdir / f"{key_hash}.cache"

    async def _get_file_lock(self, path: Path) -> asyncio.Lock:
        """Get or create a lock for a file.

        This ensures that only one operation can access a file at a time,
        even across multiple processes.

        Args:
            path: The file path.

        Returns:
            A lock for the file.
        """
        str_path = str(path)

        async with self.global_lock:
            if str_path not in self.file_locks:
                self.file_locks[str_path] = asyncio.Lock()

            return self.file_locks[str_path]

    async def get(self, key: str) -> Optional[T]:
        """Get a value from the cache.

        Args:
            key: The key to retrieve.

        Returns:
            The cached value, or None if not found or expired.

        Raises:
            BackendError: If the operation fails.
        """
        validate_cache_key(key)

        try:
            path = self._key_to_path(key)
            file_lock = await self._get_file_lock(path)

            async with file_lock:
                if not path.exists():
                    self.stats["misses"] += 1
                    logger.debug(f"Cache miss (file not found) for key: {key}")
                    return None

                try:
                    with open(path, "rb") as f:
                        file_data = f.read()

                    # Decompress if needed
                    if self.compression:
                        try:
                            import zlib

                            file_data = zlib.decompress(file_data)
                        except Exception as e:
                            logger.error(f"Failed to decompress cache file {path}: {e}")
                            await self._handle_corrupted_file(path)
                            self.stats["misses"] += 1
                            return None

                    # Parse JSON metadata
                    import json

                    data = json.loads(file_data.decode("utf-8"))

                    # Check if expired
                    expiry = data.get("expiry")
                    if expiry and time.time() > expiry:
                        await self._delete_internal(key, path)
                        self.stats["misses"] += 1
                        logger.debug(f"Cache miss (expired) for key: {key}")
                        return None

                    # Deserialize the value
                    serializer_name = data.get("serializer", "json")
                    value_data = bytes.fromhex(data["value"])

                    value = self._serializer_registry.deserialize(
                        value_data, serializer_name
                    )

                    self.stats["hits"] += 1
                    logger.debug(f"Cache hit for key: {key}")
                    return value

                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.error(f"Failed to parse cache file {path}: {e}")
                    await self._handle_corrupted_file(path)
                    self.stats["misses"] += 1
                    return None

        except (BackendError, ValidationError):
            raise
        except Exception as e:
            logger.error(f"Error reading cache file for key {key}: {e}")
            raise BackendError(
                f"Failed to get value from disk cache: {e}",
                context={"key": key, "error": str(e)},
            ) from e

    async def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """Set a value in the cache.

        Args:
            key: The key to set.
            value: The value to cache.
            ttl: Time to live in seconds. If None, the value will not expire.

        Raises:
            BackendError: If the operation fails.
            ValidationError: If the input is invalid.
        """
        validate_cache_key(key)
        if ttl is not None:
            validate_ttl(ttl)
        validate_value_size(value, self.max_value_size)

        try:
            path = self._key_to_path(key)
            file_lock = await self._get_file_lock(path)

            # Serialize the value
            value_data, serializer_name = self._serializer_registry.serialize(value)

            # Create metadata structure
            import json

            data = {
                "value": value_data.hex(),  # Store as hex string for JSON compatibility
                "serializer": serializer_name,
                "expiry": time.time() + ttl if ttl else None,
                "created": time.time(),
                "type": type(value).__name__,
            }

            async with file_lock:
                # Ensure directory exists
                path.parent.mkdir(parents=True, exist_ok=True)

                # Use atomic write pattern with a temporary file
                temp_path = path.with_suffix(".tmp")

                try:
                    json_data = json.dumps(data, separators=(",", ":")).encode("utf-8")

                    # Compress if enabled
                    if self.compression:
                        import zlib

                        json_data = zlib.compress(json_data)

                    with open(temp_path, "wb") as f:
                        f.write(json_data)

                    # Atomic rename
                    os.replace(temp_path, path)
                    self.stats["sets"] += 1
                    logger.debug(f"Set value for key: {key}")

                except Exception as e:
                    # Clean up temp file if it exists
                    if temp_path.exists():
                        try:
                            temp_path.unlink()
                        except OSError:
                            pass
                    raise e

        except (ValidationError, BackendError):
            raise
        except Exception as e:
            logger.error(f"Error writing cache file for key {key}: {e}")
            raise BackendError(
                f"Failed to set value in disk cache: {e}",
                context={"key": key, "error": str(e)},
            ) from e

    async def delete(self, key: str) -> None:
        """Delete a value from the cache.

        Args:
            key: The key to delete.

        Raises:
            BackendError: If the operation fails.
        """
        validate_cache_key(key)

        try:
            path = self._key_to_path(key)
            await self._delete_internal(key, path)

        except (ValidationError, BackendError):
            raise
        except Exception as e:
            logger.error(f"Error deleting key {key}: {e}")
            raise BackendError(
                f"Failed to delete value from disk cache: {e}",
                context={"key": key, "error": str(e)},
            ) from e

    async def _delete_internal(self, key: str, path: Optional[Path] = None) -> None:
        """Internal delete method."""
        if path is None:
            path = self._key_to_path(key)

        file_lock = await self._get_file_lock(path)

        try:
            async with file_lock:
                if path.exists():
                    path.unlink()
                    self.stats["deletes"] += 1
                    logger.debug(f"Deleted key: {key}")
        except OSError as e:
            logger.error(f"Error deleting cache file {path}: {e}")
            raise

    async def clear(self) -> None:
        """Clear all values from the cache.

        Raises:
            BackendError: If the operation fails.
        """
        try:
            import shutil

            async with self.global_lock:
                # Acquire all file locks to ensure no ongoing operations
                all_locks = list(self.file_locks.values())
                for lock in all_locks:
                    await lock.acquire()

                try:
                    # Count files before removal
                    file_count = sum(1 for _ in self.base_directory.rglob("*.cache"))

                    # Remove and recreate base directory
                    shutil.rmtree(self.base_directory)
                    self.base_directory.mkdir(parents=True, exist_ok=True)

                    logger.info(f"Cleared {file_count} cache files from disk")

                finally:
                    # Release all locks
                    for lock in all_locks:
                        lock.release()

                    # Clear the locks dictionary
                    self.file_locks.clear()

        except Exception as e:
            logger.error(f"Error clearing disk cache at {self.base_directory}: {e}")
            raise BackendError(
                f"Failed to clear disk cache: {e}",
                context={"directory": str(self.base_directory), "error": str(e)},
            ) from e

    async def cleanup_expired(self) -> int:
        """Clean up expired cache files.

        This method scans the cache directory and removes any expired cache files.
        It's useful for periodic maintenance tasks.

        Returns:
            The number of files removed.
        """
        count = 0
        now = time.time()

        try:
            # Walk the cache directory tree
            for subdir in self.base_directory.iterdir():
                if not subdir.is_dir():
                    continue

                for path in subdir.glob("*.cache"):
                    try:
                        file_lock = await self._get_file_lock(path)

                        async with file_lock:
                            with open(path, "rb") as f:
                                file_data = f.read()

                            # Decompress if needed
                            if self.compression:
                                try:
                                    import zlib

                                    file_data = zlib.decompress(file_data)
                                except Exception:
                                    # Corrupted file, remove it
                                    path.unlink()
                                    count += 1
                                    continue

                            # Parse JSON
                            try:
                                import json

                                data = json.loads(file_data.decode("utf-8"))
                            except Exception:
                                # Corrupted file, remove it
                                path.unlink()
                                count += 1
                                continue

                            # Check if expired
                            expiry = data.get("expiry")
                            if expiry and now > expiry:
                                path.unlink()
                                count += 1

                    except (OSError, FileNotFoundError):
                        # File might have been deleted by another process
                        continue

            if count > 0:
                logger.debug(f"Cleaned up {count} expired cache files")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

        return count

    async def _handle_corrupted_file(self, path: Path) -> None:
        """Handle a corrupted cache file by removing it."""
        try:
            path.unlink()
            self.stats["corrupted_files"] += 1
            logger.warning(f"Removed corrupted cache file: {path}")
        except OSError as e:
            logger.error(f"Failed to remove corrupted file {path}: {e}")

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary containing cache statistics.
        """
        file_count = 0
        total_size = 0

        try:
            for path in self.base_directory.rglob("*.cache"):
                try:
                    stat = path.stat()
                    file_count += 1
                    total_size += stat.st_size
                except OSError:
                    continue
        except Exception:
            pass

        return {
            **self.stats.copy(),
            "file_count": file_count,
            "total_size_bytes": total_size,
            "cache_directory": str(self.base_directory),
            "compression_enabled": self.compression,
            "hit_rate": (
                self.stats["hits"] / (self.stats["hits"] + self.stats["misses"])
                if (self.stats["hits"] + self.stats["misses"]) > 0
                else 0.0
            ),
        }
