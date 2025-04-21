"""Backend registry for retainit.

This module provides a registry for named cache backends, allowing users to
configure and use multiple backends simultaneously.
"""

import logging
from typing import Dict, Optional, Type

from .backends.config import BackendConfigType

logger = logging.getLogger("retainit.registry")


class BackendRegistry:
    """Registry for named cache backends.
    
    This class provides a registry for named cache backends, allowing users to
    configure and use multiple backends simultaneously.
    
    Attributes:
        _backends: Dictionary mapping backend names to configurations.
        _default_backend: Name of the default backend.
    """
    
    def __init__(self):
        """Initialize the backend registry."""
        self._backends: Dict[str, BackendConfigType] = {}
        self._default_backend: Optional[str] = None
    
    def register(self, name: str, config: BackendConfigType, default: bool = False) -> None:
        """Register a new backend with the given name and configuration.
        
        Args:
            name: The name to register the backend under.
            config: The backend configuration.
            default: Whether this backend should be the default.
        """
        self._backends[name] = config
        
        if default or self._default_backend is None:
            self._default_backend = name
            logger.debug(f"Set default backend to: {name}")
    
    def get(self, name: Optional[str] = None) -> BackendConfigType:
        """Get the backend configuration for the given name.
        
        Args:
            name: The name of the backend to get. If None, returns the default.
            
        Returns:
            The backend configuration.
            
        Raises:
            KeyError: If no backend with the given name exists.
            RuntimeError: If no default backend is set.
        """
        if name is None:
            if self._default_backend is None:
                raise RuntimeError("No default backend configured")
            return self._backends[self._default_backend]
        
        if name not in self._backends:
            raise KeyError(f"No backend registered with name '{name}'")
        
        return self._backends[name]
    
    def get_default_name(self) -> Optional[str]:
        """Get the name of the default backend.
        
        Returns:
            The name of the default backend, or None if no default is set.
        """
        return self._default_backend
    
    def set_default(self, name: str) -> None:
        """Set the default backend.
        
        Args:
            name: The name of the backend to set as default.
            
        Raises:
            KeyError: If no backend with the given name exists.
        """
        if name not in self._backends:
            raise KeyError(f"No backend registered with name '{name}'")
        
        self._default_backend = name
        logger.debug(f"Set default backend to: {name}")
    
    def list_backends(self) -> Dict[str, BackendConfigType]:
        """Get all registered backends.
        
        Returns:
            A dictionary mapping backend names to configurations.
        """
        return self._backends.copy()
    
    def remove(self, name: str) -> None:
        """Remove a backend from the registry.
        
        Args:
            name: The name of the backend to remove.
            
        Raises:
            KeyError: If no backend with the given name exists.
            RuntimeError: If trying to remove the default backend.
        """
        if name not in self._backends:
            raise KeyError(f"No backend registered with name '{name}'")
        
        if name == self._default_backend:
            raise RuntimeError(f"Cannot remove default backend: {name}")
        
        del self._backends[name]
        logger.debug(f"Removed backend: {name}")
    
    def clear(self) -> None:
        """Clear all backends from the registry."""
        self._backends.clear()
        self._default_backend = None
        logger.debug("Cleared all backends")
    
    def is_empty(self) -> bool:
        """Check if the registry is empty.
        
        Returns:
            True if no backends are registered, False otherwise.
        """
        return len(self._backends) == 0


# Global registry instance
registry = BackendRegistry()