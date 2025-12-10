"""
Onyx RepairShopr Connector - Production Grade

A custom Onyx connector for ingesting tickets, customers, assets, and
other data from RepairShopr repair shop management system.

Features:
- Full sync and incremental polling
- Checkpoint/resume for crash recovery
- Bounded LRU cache (no OOM)
- Token bucket rate limiting
- Batch enrichment (no N+1 queries)

Quick Start:
    pip install onyx-repairshopr-connector
    rs-onyx setup    # Interactive configuration
    rs-onyx test     # Verify connection
    rs-onyx sync     # Run full sync
"""

from repairshopr_connector.connector import RepairShoprConnector
from repairshopr_connector.client import (
    RepairShoprClient,
    RepairShoprAPIError,
    RepairShoprAuthError,
    RepairShoprRateLimitError,
    RepairShoprServerError,
)
from repairshopr_connector.models import (
    RSTicket,
    RSCustomer,
    RSAsset,
    RSComment,
    RSInvoice,
)
from repairshopr_connector.document_builder import (
    OnyxDocument,
    RepairShoprDocumentBuilder,
)
from repairshopr_connector.state import StateManager, SyncCheckpoint
from repairshopr_connector.cache import BoundedLRUCache, EntityCache
from repairshopr_connector.rate_limiter import TokenBucketRateLimiter

__version__ = "2.0.0"
__all__ = [
    # Main connector
    "RepairShoprConnector",

    # API client
    "RepairShoprClient",
    "RepairShoprAPIError",
    "RepairShoprAuthError",
    "RepairShoprRateLimitError",
    "RepairShoprServerError",

    # Models
    "RSTicket",
    "RSCustomer",
    "RSAsset",
    "RSComment",
    "RSInvoice",

    # Document building
    "OnyxDocument",
    "RepairShoprDocumentBuilder",

    # State management
    "StateManager",
    "SyncCheckpoint",

    # Cache
    "BoundedLRUCache",
    "EntityCache",

    # Rate limiting
    "TokenBucketRateLimiter",
]
