"""Disk cache backend implementation.

This module provides a file-system based cache backend that stores cached values
in files on disk.
"""

import asyncio
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any, Optional, TypeVar

from ..backends.base import CacheBackend

logger = logging.getLogger("retainit.backends.disk")

T = TypeVar("T")


class DiskCache(CacheBackend[T]):
    """File-system based cache backend.

    This cache stores values in files on disk, with optional compression.

    Attributes:
        base_directory: Base directory where cache files are stored.
        compression: Whether to compress cached values.
        file_locks: Dictionary of locks for each file to ensure process-safety.
    """

    def __init__(self, base_directory: str = ".cache/function_resp", compression: bool = False):
        """Initialize the disk cache.

        Args:
            base_directory: Base directory where cache files are stored.
            compression: Whether to compress cached values.
        """
        self.base_directory = Path(base_directory)
        self.compression = compression
        self.file_locks = {}  # Lock per file
        self.global_lock = asyncio.Lock()  # For operations on the file_locks dict

        # Create base directory if it doesn't exist
        self.base_directory.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str) -> Path:
        """Convert a cache key to a file path.

        To avoid having too many files in one directory, we use the first two
        characters of the key's hash as a subdirectory.

        Args:
            key: The cache key.

        Returns:
            The file path for the cache key.
        """
        import hashlib
        key_hash = hashlib.md5(key.encode()).hexdigest()
        
        # Create subdirectory based on hash prefix
        subdir = self.base_directory / key_hash[:2]
        subdir.mkdir(exist_ok=True)
        
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
        """
        path = self._key_to_path(key)
        file_lock = await self._get_file_lock(path)
        
        try:
            async with file_lock:
                if not path.exists():
                    return None
                
                with open(path, "rb") as f:
                    if self.compression:
                        import zlib
                        try:
                            data = pickle.loads(zlib.decompress(f.read()))
                        except (zlib.error, pickle.PickleError, EOFError) as e:
                            logger.error(f"Error decompressing/unpickling cache file {path}: {e}")
                            return None
                    else:
                        try:
                            data = pickle.load(f)
                        except (pickle.PickleError, EOFError) as e:
                            logger.error(f"Error unpickling cache file {path}: {e}")
                            return None
                
                # Check if expired
                expiry = data.get("expiry")
                if expiry and time.time() > expiry:
                    await self.delete(key)
                    return None
                
                return data.get("value")
        except (FileNotFoundError, OSError) as e:
            logger.error(f"Error reading cache file {path}: {e}")
            return None

    async def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """Set a value in the cache.

        Args:
            key: The key to set.
            value: The value to cache.
            ttl: Time to live in seconds. If None, the value will not expire.
        """
        path = self._key_to_path(key)
        file_lock = await self._get_file_lock(path)
        
        data = {
            "value": value,
            "expiry": time.time() + ttl if ttl else None,
            "created": time.time()
        }
        
        try:
            async with file_lock:
                # Ensure directory exists
                path.parent.mkdir(parents=True, exist_ok=True)
                
                # Use atomic write pattern with a temporary file
                temp_path = path.with_suffix('.tmp')
                
                with open(temp_path, "wb") as f:
                    if self.compression:
                        import zlib
                        f.write(zlib.compress(pickle.dumps(data)))
                    else:
                        pickle.dump(data, f)
                
                # Atomic rename
                os.replace(temp_path, path)
        except (OSError, pickle.PickleError) as e:
            logger.error(f"Error writing cache file {path}: {e}")
            # Clean up temp file if it exists
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    async def delete(self, key: str) -> None:
        """Delete a value from the cache.

        Args:
            key: The key to delete.
        """
        path = self._key_to_path(key)
        file_lock = await self._get_file_lock(path)
        
        try:
            async with file_lock:
                if path.exists():
                    path.unlink()
        except OSError as e:
            logger.error(f"Error deleting cache file {path}: {e}")

    async def clear(self) -> None:
        """Clear all values from the cache."""
        try:
            import shutil
            
            async with self.global_lock:
                # Acquire all file locks to ensure no ongoing operations
                all_locks = list(self.file_locks.values())
                for lock in all_locks:
                    await lock.acquire()
                
                try:
                    # Remove and recreate base directory
                    shutil.rmtree(self.base_directory)
                    self.base_directory.mkdir(parents=True, exist_ok=True)
                finally:
                    # Release all locks
                    for lock in all_locks:
                        lock.release()
                    
                    # Clear the locks dictionary
                    self.file_locks.clear()
        except (OSError, shutil.Error) as e:
            logger.error(f"Error clearing disk cache at {self.base_directory}: {e}")

    async def cleanup_expired(self) -> int:
        """Clean up expired cache files.

        This method scans the cache directory and removes any expired cache files.
        It's useful for periodic maintenance tasks.

        Returns:
            The number of files removed.
        """
        count = 0
        now = time.time()
        
        # Walk the cache directory tree
        for subdir in self.base_directory.iterdir():
            if not subdir.is_dir():
                continue
            
            for path in subdir.glob("*.cache"):
                try:
                    file_lock = await self._get_file_lock(path)
                    
                    async with file_lock:
                        with open(path, "rb") as f:
                            if self.compression:
                                import zlib
                                try:
                                    data = pickle.loads(zlib.decompress(f.read()))
                                except (zlib.error, pickle.PickleError, EOFError):
                                    # If we can't read it, assume it's corrupt and remove it
                                    path.unlink()
                                    count += 1
                                    continue
                            else:
                                try:
                                    data = pickle.load(f)
                                except (pickle.PickleError, EOFError):
                                    # If we can't read it, assume it's corrupt and remove it
                                    path.unlink()
                                    count += 1
                                    continue
                        
                        # Check if expired
                        expiry = data.get("expiry")
                        if expiry and now > expiry:
                            path.unlink()
                            count += 1
                except (OSError, FileNotFoundError):
                    # Ignore errors, just continue to the next file
                    continue
        
        return count