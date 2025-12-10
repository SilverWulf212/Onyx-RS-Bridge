"""
RepairShopr Connector for Onyx - Production Grade

Main connector class implementing Onyx's connector interfaces
with proper state management, caching, and batch operations.
"""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from repairshopr_connector.cache import EntityCache
from repairshopr_connector.client import RepairShoprClient
from repairshopr_connector.document_builder import (
    DOC_PREFIX_ASSET,
    DOC_PREFIX_CUSTOMER,
    DOC_PREFIX_INVOICE,
    DOC_PREFIX_TICKET,
    OnyxDocument,
    RepairShoprDocumentBuilder,
)
from repairshopr_connector.models import RSAsset, RSCustomer
from repairshopr_connector.state import StateManager, SyncCheckpoint

logger = structlog.get_logger(__name__)


# Type aliases to match Onyx conventions
SecondsSinceUnixEpoch = float
GenerateDocumentsOutput = Iterator[list[OnyxDocument]]
GenerateSlimDocumentOutput = Iterator[list[str]]


class ConnectorMissingCredentialError(Exception):
    """Raised when required credentials are not provided."""
    pass


class RepairShoprConnector:
    """
    Production-grade Onyx connector for RepairShopr.

    Improvements over v1:
    - Synchronous (no async/sync mixing)
    - Bounded LRU cache with TTL (no OOM)
    - Batch enrichment (no N+1 queries)
    - Checkpoint/resume for crash recovery
    - Configurable comment handling

    Implements:
    - LoadConnector: Full bulk indexing
    - PollConnector: Incremental updates
    - SlimConnector: Pruning deleted records

    Example:
        connector = RepairShoprConnector(subdomain="yourcompany")
        connector.load_credentials({"api_key": "your-key"})

        for batch in connector.load_from_state():
            send_to_onyx(batch)
    """

    def __init__(
        self,
        subdomain: str,
        include_tickets: bool = True,
        include_customers: bool = True,
        include_assets: bool = True,
        include_invoices: bool = False,
        include_internal_comments: bool = False,  # Security: exclude by default
        ticket_statuses: list[str] | None = None,
        batch_size: int = 50,
        state_file: str | Path | None = None,
        cache_ttl_seconds: float = 600.0,
    ):
        """
        Initialize connector.

        Args:
            subdomain: Your RS subdomain (validated)
            include_tickets: Index tickets
            include_customers: Index customer profiles
            include_assets: Index assets/devices
            include_invoices: Index invoices
            include_internal_comments: Include hidden/internal comments (security risk!)
            ticket_statuses: Only index tickets with these statuses (None = all)
            batch_size: Documents per batch
            state_file: Path for checkpoint state (None = default location)
            cache_ttl_seconds: Cache TTL for enrichment data
        """
        self.subdomain = subdomain
        self.include_tickets = include_tickets
        self.include_customers = include_customers
        self.include_assets = include_assets
        self.include_invoices = include_invoices
        self.include_internal_comments = include_internal_comments
        self.ticket_statuses = ticket_statuses
        self.batch_size = batch_size

        self._client: RepairShoprClient | None = None
        self._doc_builder: RepairShoprDocumentBuilder | None = None

        # Bounded cache for enrichment
        self._cache = EntityCache(ttl_seconds=cache_ttl_seconds)

        # State management for checkpoint/resume
        self._state_mgr = StateManager(state_file)
        self._checkpoint: SyncCheckpoint | None = None

        self._log = logger.bind(subdomain=subdomain)

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Load API credentials.

        Args:
            credentials: Dict with 'api_key'

        Raises:
            ConnectorMissingCredentialError: If api_key missing
        """
        api_key = credentials.get("api_key")
        if not api_key:
            raise ConnectorMissingCredentialError(
                "RepairShopr API key is required. "
                "Get it from RepairShopr Admin -> Profile -> API Tokens"
            )

        self._client = RepairShoprClient(
            subdomain=self.subdomain,
            api_key=api_key,
        )
        self._doc_builder = RepairShoprDocumentBuilder(
            subdomain=self.subdomain,
            include_internal_comments=self.include_internal_comments,
        )

        # Load existing state
        self._checkpoint = self._state_mgr.load()

        self._log.info(
            "Credentials loaded",
            include_tickets=self.include_tickets,
            include_customers=self.include_customers,
            include_internal_comments=self.include_internal_comments,
        )

    @property
    def client(self) -> RepairShoprClient:
        if self._client is None:
            raise RuntimeError("Call load_credentials() first")
        return self._client

    @property
    def doc_builder(self) -> RepairShoprDocumentBuilder:
        if self._doc_builder is None:
            raise RuntimeError("Call load_credentials() first")
        return self._doc_builder

    @property
    def checkpoint(self) -> SyncCheckpoint:
        if self._checkpoint is None:
            self._checkpoint = self._state_mgr.load()
        return self._checkpoint

    def _save_checkpoint(self) -> None:
        """Save current checkpoint state."""
        if self._checkpoint:
            self._state_mgr.save(self._checkpoint)

    # -------------------------------------------------------------------------
    # Batch Enrichment (eliminates N+1 queries)
    # -------------------------------------------------------------------------

    def _preload_enrichment_data(self) -> None:
        """
        Preload all customers and assets into cache.

        This eliminates N+1 queries by loading all enrichment data
        upfront in just 2 paginated fetches instead of one per ticket.
        """
        self._log.info("Preloading enrichment data (customers + assets)")

        # Load all customers
        customer_count = 0
        for customer in self.client.iter_all_customers():
            self._cache.customers.set(customer.id, customer)
            customer_count += 1

        self._log.info("Preloaded customers", count=customer_count)

        # Load all assets grouped by customer
        asset_count = 0
        assets_by_customer: dict[int, list[RSAsset]] = {}
        for asset in self.client.iter_all_assets():
            self._cache.assets.set(asset.id, asset)
            if asset.customer_id:
                assets_by_customer.setdefault(asset.customer_id, []).append(asset)
            asset_count += 1

        # Cache assets by customer for quick lookup
        for cust_id, assets in assets_by_customer.items():
            self._cache.assets_by_customer.set(cust_id, assets)

        self._log.info("Preloaded assets", count=asset_count)

    def _get_customer_cached(self, customer_id: int) -> RSCustomer | None:
        """Get customer from cache (no API call)."""
        return self._cache.customers.get(customer_id)

    def _get_customer_assets_cached(self, customer_id: int) -> list[RSAsset]:
        """Get customer's assets from cache (no API call)."""
        return self._cache.assets_by_customer.get(customer_id) or []

    # -------------------------------------------------------------------------
    # LoadConnector Interface
    # -------------------------------------------------------------------------

    def load_from_state(self) -> GenerateDocumentsOutput:
        """
        Full load with checkpoint support.

        If a previous sync was interrupted, resumes from checkpoint.
        """
        self._log.info("Starting full load")
        self.checkpoint.reset_for_new_sync("full")
        self._save_checkpoint()

        with self.client:
            # Preload enrichment data (eliminates N+1)
            self._preload_enrichment_data()

            # Load customers
            if self.include_customers and not self.checkpoint.customers_complete:
                yield from self._load_customers()
                self.checkpoint.customers_complete = True
                self._save_checkpoint()

            # Load assets
            if self.include_assets and not self.checkpoint.assets_complete:
                yield from self._load_assets()
                self.checkpoint.assets_complete = True
                self._save_checkpoint()

            # Load tickets (main content)
            if self.include_tickets and not self.checkpoint.tickets_complete:
                yield from self._load_tickets()
                self.checkpoint.tickets_complete = True
                self._save_checkpoint()

            # Load invoices
            if self.include_invoices and not self.checkpoint.invoices_complete:
                yield from self._load_invoices()
                self.checkpoint.invoices_complete = True
                self._save_checkpoint()

        # Mark complete
        self.checkpoint.mark_complete()
        self._save_checkpoint()

        self._log.info(
            "Full load complete",
            documents=self.checkpoint.documents_processed,
            errors=len(self.checkpoint.errors),
        )

    def _load_tickets(
        self,
        since: datetime | None = None,
    ) -> GenerateDocumentsOutput:
        """Load tickets with cached enrichment."""
        batch: list[OnyxDocument] = []

        for ticket in self.client.iter_all_tickets(
            since=since,
            fetch_comments=True,
            seen_ids=self.checkpoint.tickets_seen_ids,
        ):
            # Filter by status if configured
            if self.ticket_statuses and ticket.status not in self.ticket_statuses:
                continue

            # Get enrichment from cache (NO API calls!)
            customer = None
            asset = None
            if ticket.customer_id:
                customer = self._get_customer_cached(ticket.customer_id)
                assets = self._get_customer_assets_cached(ticket.customer_id)
                if assets:
                    asset = assets[0]

            # Build document
            try:
                doc = self.doc_builder.build_ticket_document(ticket, customer, asset)
                batch.append(doc)
                self.checkpoint.documents_processed += 1
            except Exception as e:
                self.checkpoint.errors.append(f"Ticket {ticket.id}: {e}")
                self._log.warning("Failed to build ticket doc", ticket_id=ticket.id, error=str(e))

            if len(batch) >= self.batch_size:
                self._log.info("Yielding ticket batch", count=len(batch))
                yield batch
                batch = []
                self._save_checkpoint()

        if batch:
            yield batch
            self._save_checkpoint()

    def _load_customers(
        self,
        since: datetime | None = None,
    ) -> GenerateDocumentsOutput:
        """Load customer documents."""
        batch: list[OnyxDocument] = []

        for customer in self.client.iter_all_customers(
            since=since,
            seen_ids=self.checkpoint.customers_seen_ids,
        ):
            try:
                doc = self.doc_builder.build_customer_document(customer)
                batch.append(doc)
                self.checkpoint.documents_processed += 1
            except Exception as e:
                self.checkpoint.errors.append(f"Customer {customer.id}: {e}")

            if len(batch) >= self.batch_size:
                self._log.info("Yielding customer batch", count=len(batch))
                yield batch
                batch = []
                self._save_checkpoint()

        if batch:
            yield batch

    def _load_assets(
        self,
        since: datetime | None = None,
    ) -> GenerateDocumentsOutput:
        """Load asset documents."""
        batch: list[OnyxDocument] = []

        for asset in self.client.iter_all_assets(
            since=since,
            seen_ids=self.checkpoint.assets_seen_ids,
        ):
            customer = self._get_customer_cached(asset.customer_id) if asset.customer_id else None

            try:
                doc = self.doc_builder.build_asset_document(asset, customer)
                batch.append(doc)
                self.checkpoint.documents_processed += 1
            except Exception as e:
                self.checkpoint.errors.append(f"Asset {asset.id}: {e}")

            if len(batch) >= self.batch_size:
                self._log.info("Yielding asset batch", count=len(batch))
                yield batch
                batch = []
                self._save_checkpoint()

        if batch:
            yield batch

    def _load_invoices(
        self,
        since: datetime | None = None,
    ) -> GenerateDocumentsOutput:
        """Load invoice documents."""
        batch: list[OnyxDocument] = []

        for invoice in self.client.iter_all_invoices(
            since=since,
            seen_ids=self.checkpoint.invoices_seen_ids,
        ):
            customer = self._get_customer_cached(invoice.customer_id) if invoice.customer_id else None

            try:
                doc = self.doc_builder.build_invoice_document(invoice, customer)
                batch.append(doc)
                self.checkpoint.documents_processed += 1
            except Exception as e:
                self.checkpoint.errors.append(f"Invoice {invoice.id}: {e}")

            if len(batch) >= self.batch_size:
                yield batch
                batch = []
                self._save_checkpoint()

        if batch:
            yield batch

    # -------------------------------------------------------------------------
    # PollConnector Interface
    # -------------------------------------------------------------------------

    def poll_source(
        self,
        start: SecondsSinceUnixEpoch,
        end: SecondsSinceUnixEpoch,
    ) -> GenerateDocumentsOutput:
        """
        Incremental poll for updates since last sync.
        """
        start_dt = datetime.fromtimestamp(start, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end, tz=timezone.utc)

        self._log.info(
            "Starting incremental poll",
            start=start_dt.isoformat(),
            end=end_dt.isoformat(),
        )

        self.checkpoint.reset_for_new_sync("poll")

        with self.client:
            # For poll, we still preload since we need enrichment
            # but it's faster because we only process changed records
            self._preload_enrichment_data()

            if self.include_customers:
                yield from self._load_customers(since=start_dt)

            if self.include_assets:
                yield from self._load_assets(since=start_dt)

            if self.include_tickets:
                yield from self._load_tickets(since=start_dt)

            if self.include_invoices:
                yield from self._load_invoices(since=start_dt)

        self.checkpoint.mark_complete()
        self._save_checkpoint()

    # -------------------------------------------------------------------------
    # SlimConnector Interface
    # -------------------------------------------------------------------------

    def retrieve_all_slim_documents(self) -> GenerateSlimDocumentOutput:
        """
        Get all document IDs for pruning deleted records.
        """
        self._log.info("Starting slim document retrieval")

        with self.client:
            batch: list[str] = []

            # Ticket IDs
            if self.include_tickets:
                for ticket in self.client.iter_all_tickets(fetch_comments=False):
                    batch.append(f"{DOC_PREFIX_TICKET}{ticket.id}")
                    if len(batch) >= self.batch_size:
                        yield batch
                        batch = []

            # Customer IDs
            if self.include_customers:
                for customer in self.client.iter_all_customers():
                    batch.append(f"{DOC_PREFIX_CUSTOMER}{customer.id}")
                    if len(batch) >= self.batch_size:
                        yield batch
                        batch = []

            # Asset IDs
            if self.include_assets:
                for asset in self.client.iter_all_assets():
                    batch.append(f"{DOC_PREFIX_ASSET}{asset.id}")
                    if len(batch) >= self.batch_size:
                        yield batch
                        batch = []

            # Invoice IDs
            if self.include_invoices:
                for invoice in self.client.iter_all_invoices():
                    batch.append(f"{DOC_PREFIX_INVOICE}{invoice.id}")
                    if len(batch) >= self.batch_size:
                        yield batch
                        batch = []

            if batch:
                yield batch

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get connector statistics for monitoring."""
        stats = {
            "subdomain": self.subdomain,
            "checkpoint": self.checkpoint.to_dict() if self._checkpoint else None,
            "cache": self._cache.get_stats(),
        }

        if self._client:
            stats["client"] = self._client.get_stats()

        return stats

    def health_check(self) -> dict[str, Any]:
        """Check connectivity and return health status."""
        if self._client is None:
            return {"status": "not_configured", "message": "Call load_credentials() first"}

        with self.client:
            return self.client.health_check()
