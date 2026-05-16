"""
Clinical Drug Safety Engine — Thread-Safe Cache

Deterministic caching layer for drug interaction results.

Cache key is computed from sorted, deduplicated, lowercased drug names.
This guarantees identical results regardless of input ordering, casing,
or duplicate entries.

Only drug-drug interaction results are cached. Patient-specific checks
(allergies, contraindications) are computed fresh every time.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Optional


class SafetyCache:
    """
    Thread-safe in-memory cache with TTL expiration.

    Properties:
    - Deterministic keys: order-independent, case-insensitive, duplicate-safe
    - TTL: entries expire after configurable duration (default 1 hour)
    - Thread-safe: all operations protected by threading.Lock
    - No external dependencies
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        """
        Initialize cache with specified TTL.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds (default: 3600 = 1 hour)
        """
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    @staticmethod
    def build_key(medicines: list[str], current_medications: list[str]) -> str:
        """
        Build a deterministic cache key from drug lists.

        Guarantees:
        - Order independent: [A, B] == [B, A]
        - Case insensitive: [Aspirin] == [aspirin]
        - Duplicate safe: [A, A, B] == [A, B]
        - Whitespace safe: [" A "] == ["A"]

        Args:
            medicines: Proposed new medicines
            current_medications: Patient's current medications

        Returns:
            SHA-256 hex digest string
        """
        normalized_meds = sorted(set(m.strip().lower() for m in medicines if m and m.strip()))
        normalized_current = sorted(set(m.strip().lower() for m in current_medications if m and m.strip()))

        key_data = json.dumps({
            "medicines": normalized_meds,
            "current_medications": normalized_current,
        }, sort_keys=True, separators=(",", ":"))

        return hashlib.sha256(key_data.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached value if it exists and hasn't expired.

        Args:
            key: Cache key (from build_key)

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None

            # Check TTL
            if time.time() - entry["timestamp"] > self._ttl:
                # Expired — remove and return None
                del self._store[key]
                return None

            return entry["value"]

    def set(self, key: str, value: Any) -> None:
        """
        Store a value in the cache.

        Args:
            key: Cache key (from build_key)
            value: Value to cache (should be serializable)
        """
        with self._lock:
            self._store[key] = {
                "value": value,
                "timestamp": time.time(),
            }

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._store.clear()

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        with self._lock:
            now = time.time()
            expired_keys = [
                k for k, v in self._store.items()
                if now - v["timestamp"] > self._ttl
            ]
            for key in expired_keys:
                del self._store[key]
            return len(expired_keys)

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        with self._lock:
            return len(self._store)


# Module-level cache instance (shared across the application)
interaction_cache = SafetyCache(ttl_seconds=3600)
