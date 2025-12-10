"""
Production-grade rate limiter using token bucket algorithm.

Handles concurrent requests properly, unlike the naive time-based approach.
"""

import threading
import time
from dataclasses import dataclass, field


@dataclass
class RateLimiterStats:
    """Statistics for monitoring rate limiter behavior."""
    requests_made: int = 0
    requests_throttled: int = 0
    total_wait_time: float = 0.0
    last_request_time: float = 0.0


class TokenBucketRateLimiter:
    """
    Thread-safe token bucket rate limiter.

    Unlike naive time-based limiters, this properly handles:
    - Concurrent requests from multiple threads
    - Burst capacity (can make several requests quickly, then wait)
    - Accurate rate limiting over time

    How it works:
    - Bucket holds up to `capacity` tokens
    - Tokens are added at `rate` tokens per second
    - Each request consumes 1 token
    - If no tokens available, wait until one is added

    Example:
        limiter = TokenBucketRateLimiter(requests_per_minute=150)

        with limiter:  # Blocks until token available
            make_api_request()
    """

    def __init__(
        self,
        requests_per_minute: int = 150,
        burst_capacity: int | None = None,
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Sustained request rate
            burst_capacity: Max burst size (defaults to 10% of per-minute rate)
        """
        self.rate = requests_per_minute / 60.0  # tokens per second
        self.capacity = burst_capacity or max(10, requests_per_minute // 10)

        self._tokens = float(self.capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

        self.stats = RateLimiterStats()

    def _refill(self) -> None:
        """Add tokens based on elapsed time. Must hold lock."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    def acquire(self, timeout: float | None = None) -> bool:
        """
        Acquire a token, blocking if necessary.

        Args:
            timeout: Max seconds to wait (None = wait forever)

        Returns:
            True if token acquired, False if timeout
        """
        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            with self._lock:
                self._refill()

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    self.stats.requests_made += 1
                    self.stats.last_request_time = time.time()
                    return True

                # Calculate wait time for next token
                wait_time = (1.0 - self._tokens) / self.rate

                # Check timeout
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    wait_time = min(wait_time, remaining)

            # Wait outside the lock
            self.stats.requests_throttled += 1
            self.stats.total_wait_time += wait_time
            time.sleep(wait_time)

    def __enter__(self) -> "TokenBucketRateLimiter":
        """Context manager that acquires a token."""
        self.acquire()
        return self

    def __exit__(self, *args) -> None:
        pass

    @property
    def available_tokens(self) -> float:
        """Current number of available tokens."""
        with self._lock:
            self._refill()
            return self._tokens

    def get_stats(self) -> dict:
        """Get rate limiter statistics for monitoring."""
        return {
            "requests_made": self.stats.requests_made,
            "requests_throttled": self.stats.requests_throttled,
            "total_wait_time_seconds": round(self.stats.total_wait_time, 2),
            "available_tokens": round(self.available_tokens, 1),
            "rate_per_minute": round(self.rate * 60, 1),
        }
