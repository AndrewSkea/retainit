"""Event system for retainit.

This module provides a flexible event system that allows users to subscribe to
various events emitted by retainit, such as cache hits, misses, and errors.
"""

import asyncio
import inspect
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union, cast

logger = logging.getLogger("retainit.events")

# Type definitions
EventData = Dict[str, Any]
SyncEventHandler = Callable[[EventData], None]
AsyncEventHandler = Callable[[EventData], asyncio.coroutine]
EventHandler = Union[SyncEventHandler, AsyncEventHandler]


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
    
    def __init__(self):
        """Initialize the event emitter."""
        self._handlers: Dict[EventType, List[EventHandler]] = {
            event_type: [] for event_type in EventType
        }
        self._enabled = True
        self._default_handlers: Dict[EventType, List[EventHandler]] = {
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
    
    def unsubscribe_all(self, event_type: Optional[EventType] = None) -> None:
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
    
    def remove_default_handler(self, event_type: EventType, handler: EventHandler) -> None:
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
        all_handlers = (
            self._default_handlers.get(event_type, []) +
            self._handlers.get(event_type, [])
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
            except Exception as e:
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
    """Decorator to subscribe a function to an event.
    
    This decorator allows for a more declarative style of event subscription.
    
    Args:
        event_type: The type of event to subscribe to.
        
    Returns:
        A decorator function that subscribes the decorated function to the event.
        
    Example:
        >>> @on(EventType.CACHE_MISS)
        >>> def handle_cache_miss(event_data):
        >>>     print(f"Cache miss: {event_data}")
    """
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


# Helper function to create a metrics handler
def create_prometheus_handler() -> Dict[EventType, EventHandler]:
    """Create event handlers that record metrics in Prometheus.
    
    Returns:
        A dictionary mapping event types to handler functions.
        
    Raises:
        ImportError: If prometheus_client is not installed.
    """
    try:
        from prometheus_client import Counter, Gauge, Histogram, Summary
    except ImportError:
        raise ImportError(
            "Prometheus metrics handler requires prometheus_client package. "
            "Install with 'pip install prometheus_client'."
        )
    
    # Define Prometheus metrics
    cache_hits = Counter(
        "retainit_cache_hits_total",
        "Number of cache hits",
        ["function", "backend"]
    )
    
    cache_misses = Counter(
        "retainit_cache_misses_total",
        "Number of cache misses",
        ["function", "backend"]
    )
    
    cache_errors = Counter(
        "retainit_cache_errors_total",
        "Number of cache errors",
        ["function", "backend", "error_type"]
    )
    
    function_calls = Counter(
        "retainit_function_calls_total",
        "Number of function calls",
        ["function"]
    )
    
    function_errors = Counter(
        "retainit_function_errors_total",
        "Number of function errors",
        ["function", "error_type"]
    )
    
    function_duration = Summary(
        "retainit_function_duration_seconds",
        "Function execution time in seconds",
        ["function"]
    )
    
    # Define handlers
    def on_cache_hit(data: EventData) -> None:
        function = data.get("function", "unknown")
        backend = data.get("backend", "unknown")
        cache_hits.labels(function=function, backend=backend).inc()
    
    def on_cache_miss(data: EventData) -> None:
        function = data.get("function", "unknown")
        backend = data.get("backend", "unknown")
        cache_misses.labels(function=function, backend=backend).inc()
    
    def on_cache_error(data: EventData) -> None:
        function = data.get("function", "unknown")
        backend = data.get("backend", "unknown")
        error_type = data.get("error_type", "unknown")
        cache_errors.labels(
            function=function,
            backend=backend,
            error_type=error_type
        ).inc()
    
    def on_function_call_start(data: EventData) -> None:
        function = data.get("function", "unknown")
        function_calls.labels(function=function).inc()
    
    def on_function_call_end(data: EventData) -> None:
        function = data.get("function", "unknown")
        duration = data.get("duration")
        if duration is not None:
            function_duration.labels(function=function).observe(duration)
    
    def on_function_error(data: EventData) -> None:
        function = data.get("function", "unknown")
        error_type = data.get("error_type", "unknown")
        function_errors.labels(
            function=function,
            error_type=error_type
        ).inc()
    
    # Return mapping of events to handlers
    return {
        EventType.CACHE_HIT: on_cache_hit,
        EventType.CACHE_MISS: on_cache_miss,
        EventType.CACHE_ERROR: on_cache_error,
        EventType.FUNCTION_CALL_START: on_function_call_start,
        EventType.FUNCTION_CALL_END: on_function_call_end,
        EventType.FUNCTION_ERROR: on_function_error,
    }


def enable_prometheus_metrics() -> None:
    """Enable Prometheus metrics for retainit events.
    
    This function sets up event handlers that record metrics in Prometheus.
    
    Raises:
        ImportError: If prometheus_client is not installed.
    """
    handlers = create_prometheus_handler()
    
    # Register all handlers
    for event_type, handler in handlers.items():
        events.subscribe(event_type, handler)