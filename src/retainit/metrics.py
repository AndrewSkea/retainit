"""Metrics collection and reporting for retainit.

This module provides functionality for collecting and reporting metrics about
cache usage, such as hit rates, latency, and error rates.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from .core import MetricEvent
from .settings import MetricsBackendType, MetricsSettings

logger = logging.getLogger("retainit.metrics")


class MetricsCollector:
    """Collects and reports metrics about cache usage.

    This class provides methods for recording metrics events and reporting them
    to various backends such as Prometheus, Datadog, and CloudWatch.

    Attributes:
        config: Metrics configuration settings.
        enabled: Whether metrics collection is enabled.
        backend: The metrics backend to use.
        namespace: The namespace to use for metrics.
        client: The metrics client instance.
    """

    def __init__(self, config: MetricsSettings):
        """Initialize the metrics collector.

        Args:
            config: Metrics configuration settings.
        """
        self.config = config
        self.enabled = config.enabled
        self.backend = config.backend
        self.namespace = config.namespace
        self._client = None
        self._lock = asyncio.Lock()
        
        if self.enabled and self.backend:
            # Initialize the metrics client lazily when first used
            logger.debug(f"Metrics collection enabled with backend: {self.backend}")

    async def _get_client(self):
        """Get or initialize the metrics client.

        Returns:
            The metrics client instance.

        Raises:
            ImportError: If the required package for the metrics backend is not installed.
        """
        if not self.enabled or self._client is not None:
            return self._client
        
        async with self._lock:
            # Check again inside the lock to avoid race conditions
            if self._client is not None:
                return self._client
            
            if self.backend == MetricsBackendType.PROMETHEUS:
                try:
                    from prometheus_client import Counter, Summary
                    
                    self._client = {
                        "cache_hits": Counter(
                            f"{self.namespace}_cache_hits_total",
                            "Number of cache hits",
                            ["function", "backend"]
                        ),
                        "cache_misses": Counter(
                            f"{self.namespace}_cache_misses_total",
                            "Number of cache misses",
                            ["function", "backend"]
                        ),
                        "cache_errors": Counter(
                            f"{self.namespace}_cache_errors_total",
                            "Number of cache errors",
                            ["function", "backend", "error_type"]
                        ),
                        "function_calls": Counter(
                            f"{self.namespace}_function_calls_total",
                            "Number of function calls",
                            ["function"]
                        ),
                        "function_errors": Counter(
                            f"{self.namespace}_function_errors_total",
                            "Number of function errors",
                            ["function", "error_type"]
                        ),
                        "function_duration": Summary(
                            f"{self.namespace}_function_duration_seconds",
                            "Function execution time in seconds",
                            ["function"]
                        ),
                    }
                except ImportError:
                    logger.warning(
                        "Prometheus metrics enabled but 'prometheus_client' not installed. "
                        "Install with 'pip install retainit[prometheus]'"
                    )
                    self.enabled = False
            
            elif self.backend == MetricsBackendType.DATADOG:
                try:
                    import datadog
                    # Initialize datadog client
                    datadog.initialize()
                    self._client = datadog
                except ImportError:
                    logger.warning(
                        "Datadog metrics enabled but 'datadog' not installed. "
                        "Install with 'pip install retainit[datadog]'"
                    )
                    self.enabled = False
            
            elif self.backend == MetricsBackendType.CLOUDWATCH:
                try:
                    import boto3
                    self._client = boto3.client('cloudwatch')
                except ImportError:
                    logger.warning(
                        "CloudWatch metrics enabled but 'boto3' not installed. "
                        "Install with 'pip install retainit[cloudwatch]'"
                    )
                    self.enabled = False
            
            elif self.backend == MetricsBackendType.STATSD:
                try:
                    import statsd
                    self._client = statsd.StatsClient('localhost', 8125, prefix=self.namespace)
                except ImportError:
                    logger.warning(
                        "StatsD metrics enabled but 'statsd' not installed. "
                        "Install with 'pip install statsd'"
                    )
                    self.enabled = False
            
            return self._client

    async def record_metric(
        self,
        event: MetricEvent,
        function_name: str,
        backend: Optional[str] = None,
        error_type: Optional[str] = None,
        duration: Optional[float] = None,
    ) -> None:
        """Record a metric event.

        Args:
            event: The metric event to record.
            function_name: The name of the function being cached.
            backend: Optional backend name for cache operations.
            error_type: Optional error type for error events.
            duration: Optional duration for function call events.
        """
        if not self.enabled:
            return
        
        client = await self._get_client()
        if client is None:
            return
        
        # Handle based on backend type
        if self.backend == MetricsBackendType.PROMETHEUS:
            if event == MetricEvent.CACHE_HIT:
                client["cache_hits"].labels(function=function_name, backend=backend or "unknown").inc()
            elif event == MetricEvent.CACHE_MISS:
                client["cache_misses"].labels(function=function_name, backend=backend or "unknown").inc()
            elif event == MetricEvent.CACHE_ERROR:
                client["cache_errors"].labels(
                    function=function_name,
                    backend=backend or "unknown",
                    error_type=error_type or "unknown"
                ).inc()
            elif event == MetricEvent.FUNCTION_CALL:
                client["function_calls"].labels(function=function_name).inc()
            elif event == MetricEvent.FUNCTION_ERROR:
                client["function_errors"].labels(
                    function=function_name,
                    error_type=error_type or "unknown"
                ).inc()
            
            if duration is not None and event == MetricEvent.FUNCTION_CALL:
                client["function_duration"].labels(function=function_name).observe(duration)
        
        elif self.backend == MetricsBackendType.DATADOG:
            tags = [f"function:{function_name}"]
            if backend:
                tags.append(f"backend:{backend}")
            if error_type:
                tags.append(f"error_type:{error_type}")
            
            metric_name = f"{self.namespace}.{event.value}"
            
            if event in (
                MetricEvent.CACHE_HIT,
                MetricEvent.CACHE_MISS,
                MetricEvent.CACHE_ERROR,
                MetricEvent.FUNCTION_CALL,
                MetricEvent.FUNCTION_ERROR,
            ):
                client.statsd.increment(metric_name, tags=tags)
            
            if duration is not None and event == MetricEvent.FUNCTION_CALL:
                client.statsd.histogram(f"{self.namespace}.function_duration", duration, tags=tags)
        
        elif self.backend == MetricsBackendType.CLOUDWATCH:
            dimensions = [{"Name": "Function", "Value": function_name}]
            if backend:
                dimensions.append({"Name": "Backend", "Value": backend})
            if error_type:
                dimensions.append({"Name": "ErrorType", "Value": error_type})
            
            metric_data = []
            
            if event in (
                MetricEvent.CACHE_HIT,
                MetricEvent.CACHE_MISS,
                MetricEvent.CACHE_ERROR,
                MetricEvent.FUNCTION_CALL,
                MetricEvent.FUNCTION_ERROR,
            ):
                metric_data.append({
                    "MetricName": event.value,
                    "Dimensions": dimensions,
                    "Value": 1,
                    "Unit": "Count"
                })
            
            if duration is not None and event == MetricEvent.FUNCTION_CALL:
                metric_data.append({
                    "MetricName": "FunctionDuration",
                    "Dimensions": dimensions,
                    "Value": duration,
                    "Unit": "Seconds"
                })
            
            if metric_data:
                try:
                    client.put_metric_data(
                        Namespace=self.namespace,
                        MetricData=metric_data
                    )
                except Exception as e:
                    logger.error(f"Error sending CloudWatch metrics: {e}")
        
        elif self.backend == MetricsBackendType.STATSD:
            metric_name = f"{event.value}"
            
            if event in (
                MetricEvent.CACHE_HIT,
                MetricEvent.CACHE_MISS,
                MetricEvent.CACHE_ERROR,
                MetricEvent.FUNCTION_CALL,
                MetricEvent.FUNCTION_ERROR,
            ):
                client.incr(metric_name)
            
            if duration is not None and event == MetricEvent.FUNCTION_CALL:
                client.timing("function_duration", duration * 1000)  # Convert to milliseconds