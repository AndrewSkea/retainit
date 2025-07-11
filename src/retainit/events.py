"""Event system for retainit.

This module provides a flexible event system that allows users to subscribe to
various events emitted by retainit, such as cache hits, misses, and errors.
"""

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any

logger = logging.getLogger("retainit.events")

# Type definitions
EventData = dict[str, Any]
SyncEventHandler = Callable[[EventData], None]
AsyncEventHandler = Callable[[EventData], Coroutine]
EventHandler = SyncEventHandler | AsyncEventHandler


class EventType(str, Enum):
    """Types of events that can be emitted by retainit."""

    # Cache events
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    CACHE_SET = "cache_set"
    CACHE_DELETE = "cache_delete"
    CACHE_CLEAR = "cache_clear"
    CACHE_ERROR = "cache_error"

    # Function events
    FUNCTION_CALL_START = "function_call_start"
    FUNCTION_CALL_END = "function_call_end"
    FUNCTION_ERROR = "function_error"

    # Lifecycle events
    BACKEND_INIT = "backend_init"
    BACKEND_CLOSE = "backend_close"


class EventEmitter:
    """Manages event subscriptions and emits events.

    This class allows subscribing to and unsubscribing from specific event types,
    as well as emitting events with associated data.

    Attributes:
        _handlers: Dictionary mapping event types to lists of handlers.
        _enabled: Whether event emission is enabled.
        _default_handlers: Dictionary mapping event types to default handlers.

    """

    def __init__(self) -> None:
        """Initialize the event emitter."""
        self._handlers: dict[EventType, list[EventHandler]] = {
            event_type: [] for event_type in EventType
        }
        self._enabled = True
        self._default_handlers: dict[EventType, list[EventHandler]] = {
            event_type: [] for event_type in EventType
        }
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Subscribe to an event.

        Args:
            event_type: The type of event to subscribe to.
            handler: The function to call when the event occurs.

        """
        if event_type not in self._handlers:
            raise ValueError(f"Unknown event type: {event_type}")

        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Unsubscribe from an event.

        Args:
            event_type: The type of event to unsubscribe from.
            handler: The handler to remove.

        """
        if event_type not in self._handlers:
            raise ValueError(f"Unknown event type: {event_type}")

        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def unsubscribe_all(self, event_type: EventType | None = None) -> None:
        """Unsubscribe all handlers from an event type or all events.

        Args:
            event_type: The type of event to unsubscribe all handlers from.
                If None, unsubscribe all handlers from all events.

        """
        if event_type is None:
            for et in self._handlers:
                self._handlers[et] = []
        elif event_type in self._handlers:
            self._handlers[event_type] = []

    def add_default_handler(self, event_type: EventType, handler: EventHandler) -> None:
        """Add a default handler for an event type.

        Default handlers are always called when an event is emitted, even if no
        user has explicitly subscribed to the event.

        Args:
            event_type: The type of event to add a default handler for.
            handler: The default handler function.

        """
        if event_type not in self._default_handlers:
            raise ValueError(f"Unknown event type: {event_type}")

        if handler not in self._default_handlers[event_type]:
            self._default_handlers[event_type].append(handler)

    def remove_default_handler(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        """Remove a default handler for an event type.

        Args:
            event_type: The type of event to remove the default handler from.
            handler: The default handler function to remove.

        """
        if event_type not in self._default_handlers:
            raise ValueError(f"Unknown event type: {event_type}")

        if handler in self._default_handlers[event_type]:
            self._default_handlers[event_type].remove(handler)

    async def emit(self, event_type: EventType, data: EventData) -> None:
        """Emit an event.

        This method calls all handlers subscribed to the given event type with
        the provided data.

        Args:
            event_type: The type of event to emit.
            data: Data associated with the event.

        """
        if not self._enabled:
            return

        if event_type not in self._handlers:
            logger.warning(f"Attempted to emit unknown event type: {event_type}")
            return

        # Add standard fields to all events
        enriched_data = data.copy()
        enriched_data["event_type"] = event_type.value
        enriched_data["timestamp"] = time.time()

        # Get all handlers (default + user subscribed)
        all_handlers = self._default_handlers.get(event_type, []) + self._handlers.get(
            event_type,
            [],
        )

        # Call all handlers for this event type
        for handler in all_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    # Async handler
                    await handler(enriched_data)
                else:
                    # Sync handler
                    handler(enriched_data)
            except Exception as e:  # noqa: BLE001
                # Prevent event handler exceptions from affecting the main code
                logger.error(f"Error in event handler for {event_type}: {str(e)}")

    def enable(self) -> None:
        """Enable event emission."""
        self._enabled = True

    def disable(self) -> None:
        """Disable event emission."""
        self._enabled = False

    def is_enabled(self) -> bool:
        """Check if event emission is enabled.

        Returns:
            Whether event emission is enabled.

        """
        return self._enabled


# Global event emitter instance
events = EventEmitter()


# Helper decorator to subscribe to events
def on(event_type: EventType) -> Callable[[EventHandler], EventHandler]:
    """Decorator subscribes a function to an event.

    This decorator allows for a more declarative style of event subscription.

    Args:
        event_type: The type of event to subscribe to.

    Returns:
        A decorator function that subscribes the decorated function to the event.

    Example:
        >>> @on(EventType.CACHE_MISS)
        >>> def handle_cache_miss(event_data):
        >>>     print(f"Cache miss: {event_data}")

    """  # noqa: D401

    def decorator(func: EventHandler) -> EventHandler:
        events.subscribe(event_type, func)
        return func

    return decorator


# Add some standard logging handlers
def setup_logging_handlers(level: int = logging.INFO) -> None:
    """Set up default logging handlers for events.

    Args:
        level: The logging level to use for event logs.

    """
    logger.setLevel(level)

    def log_cache_error(data: EventData) -> None:
        logger.error(f"Cache error: {data.get('error')} for key: {data.get('key')}")

    def log_function_error(data: EventData) -> None:
        logger.error(f"Function error: {data.get('error')} in {data.get('function')}")

    # Add default handlers for error events
    events.add_default_handler(EventType.CACHE_ERROR, log_cache_error)
    events.add_default_handler(EventType.FUNCTION_ERROR, log_function_error)
