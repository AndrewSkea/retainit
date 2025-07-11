"""Simple test script."""

import time

import retainit
from retainit import retain
from retainit.backends.config import MemoryConfig

retainit.register_backend(
    "memory",
    MemoryConfig(
        max_size=100,
        ttl=10,
        compression=False,
    ),
    default=True,
)


@retain
def test_function_10() -> int:
    """Test func with sleep."""
    time.sleep(10)
    return 10


if __name__ == "__main__":
    stime = time.time()
    test_function_10()
    print(f"FUNC call 1 : {round(time.time() - stime, 2)}")  # 10.0s
    test_function_10()
    print(f"FUNC call 2 : {round(time.time() - stime, 2)}")  # 10.1s
    time.sleep(10)  # Wait until after ttl has expired
    test_function_10()
    print(
        f"FUNC call 3 : {round(time.time() - stime, 2)}",
    )  # 30.1s (10s sleep + ttl expired)
    if time.time() - stime < 30:
        raise RuntimeError(f"We haven't cached properly, took {time.time() - stime}")
