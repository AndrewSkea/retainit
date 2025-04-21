"""Example of using retainit with Prometheus metrics.

This example demonstrates how to integrate retainit with Prometheus metrics
for monitoring and observability.
"""

import asyncio
import random
import time

from prometheus_client import Summary, start_http_server

import retainit
from retainit import EventType, enable_prometheus_metrics, events, retain

# Define a custom Prometheus metric (in addition to the automatic ones)
REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing request')


# Define some test functions
@retain(ttl=30)
def fetch_user(user_id):
    """Simulate fetching a user from a database."""
    # Simulate variable processing time
    duration = random.uniform(0.1, 0.5)
    time.sleep(duration)
    return {
        "id": user_id,
        "name": f"User {user_id}",
        "email": f"user{user_id}@example.com"
    }


@retain(ttl=60)
def fetch_product(product_id):
    """Simulate fetching a product from a database."""
    # Simulate variable processing time
    duration = random.uniform(0.2, 0.8)
    time.sleep(duration)
    return {
        "id": product_id,
        "name": f"Product {product_id}",
        "price": round(random.uniform(10, 1000), 2)
    }


@retain(ttl=15)
async def fetch_orders(user_id, limit=5):
    """Simulate fetching orders for a user."""
    # Simulate async API call
    await asyncio.sleep(random.uniform(0.3, 0.7))
    
    # Generate random orders
    orders = []
    for i in range(limit):
        order_id = random.randint(1000, 9999)
        product_id = random.randint(1, 100)
        orders.append({
            "id": order_id,
            "user_id": user_id,
            "product_id": product_id,
            "quantity": random.randint(1, 5),
            "date": f"2023-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
        })
    
    return orders


# Example handler for a web endpoint
@REQUEST_TIME.time()
def process_user_request(user_id):
    """Process a user request, measuring the total time."""
    # Fetch user data
    user = fetch_user(user_id)
    
    # Fetch products the user might be interested in
    recommended_products = [
        fetch_product(random.randint(1, 100))
        for _ in range(3)
    ]
    
    # Combine results
    return {
        "user": user,
        "recommended_products": recommended_products
    }


async def process_orders_request(user_id):
    """Process an orders request asynchronously."""
    # Fetch user data
    user = fetch_user(user_id)
    
    # Fetch recent orders
    orders = await fetch_orders(user_id, limit=3)
    
    # Enrich orders with product details
    for order in orders:
        order["product"] = fetch_product(order["product_id"])
    
    # Combine results
    return {
        "user": user,
        "orders": orders
    }


async def simulate_traffic():
    """Simulate traffic to generate metrics."""
    while True:
        # Simulate multiple user requests with some cache hits and misses
        for _ in range(10):
            user_id = random.randint(1, 20)  # Use a small range to get cache hits
            process_user_request(user_id)
        
        # Simulate async requests
        for _ in range(5):
            user_id = random.randint(1, 20)
            await process_orders_request(user_id)
        
        # Wait a bit before the next batch
        await asyncio.sleep(2)


async def main():
    # Initialize retainit
    retainit.init(backend="memory", ttl=60)
    
    # Enable Prometheus metrics
    enable_prometheus_metrics()
    
    # Start Prometheus HTTP server
    start_http_server(8000)
    print("Prometheus metrics server started on port 8000")
    print("Visit http://localhost:8000 to see metrics")
    
    # Print available metrics
    print("\nAvailable metrics:")
    print("- retainit_cache_hits_total")
    print("- retainit_cache_misses_total")
    print("- retainit_cache_errors_total")
    print("- retainit_function_calls_total")
    print("- retainit_function_errors_total")
    print("- retainit_function_duration_seconds")
    print("- request_processing_seconds")
    
    # Log some information about events
    print("\nSimulating traffic to generate metrics...")
    print("Press Ctrl+C to stop\n")
    
    # Run traffic simulation
    await simulate_traffic()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")