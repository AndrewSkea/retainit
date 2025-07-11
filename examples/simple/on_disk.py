"""Simple test script."""

import time

import retainit
from retainit import retain
from retainit.backends.config import DiskConfig

retainit.register_backend(
    "cache_dir",
    DiskConfig(
        base_path=".cache",
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
    print(f"FUNC call 1 : {round(time.time() - stime, 2)}")
    test_function_10()
    print(f"FUNC call 2 : {round(time.time() - stime, 2)}")
    test_function_10()
    print(f"FUNC call 3 : {round(time.time() - stime, 2)}")
    if time.time() - stime > 12:
        raise RuntimeError(f"We haven't cached properly, took {time.time() - stime}")
