"""
Bounded LRU Cache with TTL

Unlike unbounded dicts that grow forever and OOM,
this cache has size limits and time-based expiration.
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TypeVar, Generic, Callable, Any

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class CacheEntry(Generic[V]):
    """Cache entry with value and expiration time."""
    value: V
    expires_at: float


class BoundedLRUCache(Generic[K, V]):
    """
    Thread-safe LRU cache with size limit and TTL.

    Features:
    - Maximum size (evicts least-recently-used when full)
    - Time-to-live (entries expire after TTL seconds)
    - Thread-safe for concurrent access
    - Statistics for monitoring

    Example:
        cache = BoundedLRUCache[int, Customer](max_size=1000, ttl_seconds=300)

        cache.set(123, customer)
        customer = cache.get(123)  # Returns customer or None

        # With loader function
        customer = cache.get_or_load(123, lambda: fetch_customer(123))
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: float = 300.0,  # 5 minutes default
    ):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of entries
            ttl_seconds: Time-to-live in seconds (0 = no expiration)
        """
        if max_size <= 0:
            raise ValueError("max_size must be positive")

        self.max_size = max_size
        self.ttl_seconds = ttl_seconds

        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = threading.Lock()

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: K) -> V | None:
        """
        Get value from cache.

        Returns None if key not found or expired.
        Moves accessed item to end (most recently used).
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            # Check expiration
            if self.ttl_seconds > 0 and time.monotonic() > entry.expires_at:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return entry.value

    def set(self, key: K, value: V) -> None:
        """
        Set value in cache.

        Evicts LRU items if cache is full.
        """
        expires_at = (
            time.monotonic() + self.ttl_seconds
            if self.ttl_seconds > 0
            else float("inf")
        )

        with self._lock:
            # Remove existing entry if present
            if key in self._cache:
                del self._cache[key]

            # Evict LRU items if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
                self._evictions += 1

            # Add new entry
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    def get_or_load(self, key: K, loader: Callable[[], V | None]) -> V | None:
        """
        Get value from cache, or load it if not present.

        This is the preferred method for most use cases as it
        handles cache misses automatically.

        Args:
            key: Cache key
            loader: Function to call on cache miss (should return value or None)

        Returns:
            Cached or loaded value, or None if loader returns None
        """
        # Try cache first
        value = self.get(key)
        if value is not None:
            return value

        # Load and cache
        value = loader()
        if value is not None:
            self.set(key, value)

        return value

    def invalidate(self, key: K) -> bool:
        """
        Remove key from cache.

        Returns True if key was present.
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from cache."""
        with self._lock:
            self._cache.clear()

    def __contains__(self, key: K) -> bool:
        """Check if key is in cache (and not expired)."""
        return self.get(key) is not None

    def __len__(self) -> int:
        """Return number of entries (may include expired)."""
        return len(self._cache)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics for monitoring."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "evictions": self._evictions,
        }

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns number of entries removed.
        Call this periodically if you have lots of entries
        that might expire without being accessed.
        """
        now = time.monotonic()
        removed = 0

        with self._lock:
            # Can't modify dict while iterating, so collect keys first
            expired_keys = [
                key for key, entry in self._cache.items()
                if self.ttl_seconds > 0 and now > entry.expires_at
            ]

            for key in expired_keys:
                del self._cache[key]
                removed += 1

        return removed


class EntityCache:
    """
    Specialized cache for RepairShopr entities.

    Provides typed caches for customers and assets with
    appropriate size limits based on typical shop sizes.
    """

    def __init__(
        self,
        customer_max_size: int = 10000,
        asset_max_size: int = 50000,
        ttl_seconds: float = 600.0,  # 10 minutes
    ):
        self.customers: BoundedLRUCache[int, Any] = BoundedLRUCache(
            max_size=customer_max_size,
            ttl_seconds=ttl_seconds,
        )
        self.assets: BoundedLRUCache[int, Any] = BoundedLRUCache(
            max_size=asset_max_size,
            ttl_seconds=ttl_seconds,
        )
        self.assets_by_customer: BoundedLRUCache[int, list[Any]] = BoundedLRUCache(
            max_size=customer_max_size,
            ttl_seconds=ttl_seconds,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get combined cache statistics."""
        return {
            "customers": self.customers.get_stats(),
            "assets": self.assets.get_stats(),
            "assets_by_customer": self.assets_by_customer.get_stats(),
        }

    def clear_all(self) -> None:
        """Clear all caches."""
        self.customers.clear()
        self.assets.clear()
        self.assets_by_customer.clear()
