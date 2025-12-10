"""
RepairShopr Connector for Onyx

Main connector class that implements Onyx's connector interfaces
for bulk loading, polling, and pruning RepairShopr data.
"""

import asyncio
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import structlog

from repairshopr_connector.client import RepairShoprClient
from repairshopr_connector.document_builder import (
    DOC_PREFIX_ASSET,
    DOC_PREFIX_CUSTOMER,
    DOC_PREFIX_INVOICE,
    DOC_PREFIX_TICKET,
    OnyxDocument,
    RepairShoprDocumentBuilder,
)
from repairshopr_connector.models import RSAsset, RSCustomer, RSTicket

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
    Onyx connector for RepairShopr repair shop management system.

    Implements three connector types:
    - LoadConnector: Full bulk indexing of all data
    - PollConnector: Incremental updates based on timestamps
    - SlimConnector: Lightweight ID-only checks for pruning

    Configuration:
        subdomain: Your RepairShopr subdomain (e.g., 'yourcompany')
        include_tickets: Index tickets (default: True)
        include_customers: Index customers (default: True)
        include_assets: Index assets (default: True)
        include_invoices: Index invoices (default: False)
        ticket_statuses: Filter tickets by status (default: all)
        batch_size: Documents per batch (default: 50)

    Usage:
        connector = RepairShoprConnector(subdomain="yourcompany")
        connector.load_credentials({"api_key": "your-api-key"})

        # Full load
        for doc_batch in connector.load_from_state():
            process_documents(doc_batch)

        # Incremental poll
        for doc_batch in connector.poll_source(start_time, end_time):
            process_documents(doc_batch)
    """

    def __init__(
        self,
        subdomain: str,
        include_tickets: bool = True,
        include_customers: bool = True,
        include_assets: bool = True,
        include_invoices: bool = False,
        ticket_statuses: list[str] | None = None,
        batch_size: int = 50,
    ):
        self.subdomain = subdomain
        self.include_tickets = include_tickets
        self.include_customers = include_customers
        self.include_assets = include_assets
        self.include_invoices = include_invoices
        self.ticket_statuses = ticket_statuses
        self.batch_size = batch_size

        self._client: RepairShoprClient | None = None
        self._doc_builder: RepairShoprDocumentBuilder | None = None

        # Caches for enrichment lookups
        self._customer_cache: dict[int, RSCustomer] = {}
        self._asset_cache: dict[int, RSAsset] = {}

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Load API credentials from Onyx's credential store.

        Args:
            credentials: Dictionary containing 'api_key'

        Raises:
            ConnectorMissingCredentialError: If api_key is missing
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
        self._doc_builder = RepairShoprDocumentBuilder(subdomain=self.subdomain)

        logger.info(
            "Credentials loaded",
            subdomain=self.subdomain,
            include_tickets=self.include_tickets,
            include_customers=self.include_customers,
            include_assets=self.include_assets,
        )

    @property
    def client(self) -> RepairShoprClient:
        if self._client is None:
            raise RuntimeError("Credentials not loaded. Call load_credentials() first.")
        return self._client

    @property
    def doc_builder(self) -> RepairShoprDocumentBuilder:
        if self._doc_builder is None:
            raise RuntimeError("Credentials not loaded. Call load_credentials() first.")
        return self._doc_builder

    def _run_async(self, coro):
        """Run an async coroutine synchronously."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(coro)

    async def _get_customer(self, customer_id: int) -> RSCustomer | None:
        """Get customer with caching."""
        if customer_id in self._customer_cache:
            return self._customer_cache[customer_id]

        try:
            customer = await self.client.get_customer(customer_id)
            self._customer_cache[customer_id] = customer
            return customer
        except Exception as e:
            logger.warning("Failed to fetch customer", customer_id=customer_id, error=str(e))
            return None

    async def _get_asset(self, asset_id: int) -> RSAsset | None:
        """Get asset with caching."""
        if asset_id in self._asset_cache:
            return self._asset_cache[asset_id]

        try:
            asset = await self.client.get_asset(asset_id)
            self._asset_cache[asset_id] = asset
            return asset
        except Exception as e:
            logger.warning("Failed to fetch asset", asset_id=asset_id, error=str(e))
            return None

    async def _enrich_ticket(self, ticket: RSTicket) -> tuple[RSCustomer | None, RSAsset | None]:
        """Fetch related customer and asset for a ticket."""
        customer = None
        asset = None

        if ticket.customer_id:
            customer = await self._get_customer(ticket.customer_id)

        # Get first linked asset if available
        if ticket.assets:
            asset = ticket.assets[0]
        elif ticket.customer_id:
            # Try to get customer's primary asset
            try:
                assets_response = await self.client.get_assets(customer_id=ticket.customer_id)
                if assets_response.assets:
                    asset = assets_response.assets[0]
            except Exception:
                pass

        return customer, asset

    # -------------------------------------------------------------------------
    # LoadConnector Interface
    # -------------------------------------------------------------------------

    def load_from_state(self) -> GenerateDocumentsOutput:
        """
        Full load - fetch all documents from RepairShopr.

        This is used for initial indexing and periodic full refreshes.
        Yields batches of documents to avoid memory issues.
        """
        logger.info("Starting full load from RepairShopr")

        async def _load_all():
            async with self.client:
                # Load customers first (for enrichment)
                if self.include_customers:
                    async for batch in self._load_customers():
                        yield batch

                # Load assets (for enrichment)
                if self.include_assets:
                    async for batch in self._load_assets():
                        yield batch

                # Load tickets (main content)
                if self.include_tickets:
                    async for batch in self._load_tickets():
                        yield batch

                # Load invoices
                if self.include_invoices:
                    async for batch in self._load_invoices():
                        yield batch

        # Convert async generator to sync
        async def collect_batches():
            batches = []
            async for batch in _load_all():
                batches.append(batch)
            return batches

        batches = self._run_async(collect_batches())
        for batch in batches:
            yield batch

    async def _load_tickets(
        self,
        since: datetime | None = None,
    ) -> Iterator[list[OnyxDocument]]:
        """Load tickets with enrichment."""
        batch: list[OnyxDocument] = []
        count = 0

        async for ticket in self.client.iter_all_tickets(since=since):
            # Filter by status if configured
            if self.ticket_statuses and ticket.status not in self.ticket_statuses:
                continue

            # Enrich with customer and asset data
            customer, asset = await self._enrich_ticket(ticket)

            # Build document
            doc = self.doc_builder.build_ticket_document(ticket, customer, asset)
            batch.append(doc)
            count += 1

            if len(batch) >= self.batch_size:
                logger.info("Yielding ticket batch", count=count)
                yield batch
                batch = []

        if batch:
            logger.info("Yielding final ticket batch", count=count)
            yield batch

    async def _load_customers(
        self,
        since: datetime | None = None,
    ) -> Iterator[list[OnyxDocument]]:
        """Load customer documents."""
        batch: list[OnyxDocument] = []
        count = 0

        async for customer in self.client.iter_all_customers(since=since):
            # Cache for ticket enrichment
            self._customer_cache[customer.id] = customer

            # Build document
            doc = self.doc_builder.build_customer_document(customer)
            batch.append(doc)
            count += 1

            if len(batch) >= self.batch_size:
                logger.info("Yielding customer batch", count=count)
                yield batch
                batch = []

        if batch:
            logger.info("Yielding final customer batch", count=count)
            yield batch

    async def _load_assets(
        self,
        since: datetime | None = None,
    ) -> Iterator[list[OnyxDocument]]:
        """Load asset documents."""
        batch: list[OnyxDocument] = []
        count = 0

        async for asset in self.client.iter_all_assets(since=since):
            # Cache for ticket enrichment
            self._asset_cache[asset.id] = asset

            # Get owner customer
            customer = None
            if asset.customer_id:
                customer = await self._get_customer(asset.customer_id)

            # Build document
            doc = self.doc_builder.build_asset_document(asset, customer)
            batch.append(doc)
            count += 1

            if len(batch) >= self.batch_size:
                logger.info("Yielding asset batch", count=count)
                yield batch
                batch = []

        if batch:
            logger.info("Yielding final asset batch", count=count)
            yield batch

    async def _load_invoices(
        self,
        since: datetime | None = None,
    ) -> Iterator[list[OnyxDocument]]:
        """Load invoice documents."""
        batch: list[OnyxDocument] = []
        count = 0

        async for invoice in self.client.iter_all_invoices(since=since):
            # Get customer
            customer = None
            if invoice.customer_id:
                customer = await self._get_customer(invoice.customer_id)

            # Build document
            doc = self.doc_builder.build_invoice_document(invoice, customer)
            batch.append(doc)
            count += 1

            if len(batch) >= self.batch_size:
                logger.info("Yielding invoice batch", count=count)
                yield batch
                batch = []

        if batch:
            logger.info("Yielding final invoice batch", count=count)
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
        Incremental poll - fetch documents updated since last poll.

        Args:
            start: Unix timestamp of last successful poll
            end: Unix timestamp of current poll

        Yields:
            Batches of documents updated in the time range
        """
        start_dt = datetime.fromtimestamp(start, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end, tz=timezone.utc)

        logger.info(
            "Starting incremental poll",
            start=start_dt.isoformat(),
            end=end_dt.isoformat(),
        )

        async def _poll_all():
            async with self.client:
                # Poll customers
                if self.include_customers:
                    async for batch in self._load_customers(since=start_dt):
                        yield batch

                # Poll assets
                if self.include_assets:
                    async for batch in self._load_assets(since=start_dt):
                        yield batch

                # Poll tickets
                if self.include_tickets:
                    async for batch in self._load_tickets(since=start_dt):
                        yield batch

                # Poll invoices
                if self.include_invoices:
                    async for batch in self._load_invoices(since=start_dt):
                        yield batch

        async def collect_batches():
            batches = []
            async for batch in _poll_all():
                batches.append(batch)
            return batches

        batches = self._run_async(collect_batches())
        for batch in batches:
            yield batch

    # -------------------------------------------------------------------------
    # SlimConnector Interface
    # -------------------------------------------------------------------------

    def retrieve_all_slim_documents(self) -> GenerateSlimDocumentOutput:
        """
        Retrieve only document IDs for pruning deleted records.

        This is a lightweight check to identify documents that
        have been deleted from RepairShopr and should be removed
        from Onyx.

        Yields:
            Batches of document IDs
        """
        logger.info("Starting slim document retrieval for pruning")

        async def _get_all_ids():
            async with self.client:
                ids: list[str] = []

                # Ticket IDs
                if self.include_tickets:
                    async for ticket_id in self.client.get_all_ticket_ids():
                        ids.append(f"{DOC_PREFIX_TICKET}{ticket_id}")
                        if len(ids) >= self.batch_size:
                            yield ids
                            ids = []

                # Customer IDs
                if self.include_customers:
                    async for customer_id in self.client.get_all_customer_ids():
                        ids.append(f"{DOC_PREFIX_CUSTOMER}{customer_id}")
                        if len(ids) >= self.batch_size:
                            yield ids
                            ids = []

                # Asset IDs
                if self.include_assets:
                    async for asset_id in self.client.get_all_asset_ids():
                        ids.append(f"{DOC_PREFIX_ASSET}{asset_id}")
                        if len(ids) >= self.batch_size:
                            yield ids
                            ids = []

                if ids:
                    yield ids

        async def collect_batches():
            batches = []
            async for batch in _get_all_ids():
                batches.append(batch)
            return batches

        batches = self._run_async(collect_batches())
        for batch in batches:
            yield batch


# Convenience function for standalone testing
def main():
    """Test the connector with environment variables."""
    import os

    subdomain = os.environ.get("RS_SUBDOMAIN")
    api_key = os.environ.get("RS_API_KEY")

    if not subdomain or not api_key:
        print("Set RS_SUBDOMAIN and RS_API_KEY environment variables")
        return

    connector = RepairShoprConnector(subdomain=subdomain)
    connector.load_credentials({"api_key": api_key})

    print("Testing full load...")
    for batch in connector.load_from_state():
        print(f"Received batch of {len(batch)} documents")
        for doc in batch[:3]:  # Print first 3 of each batch
            print(f"  - {doc.semantic_identifier}")


if __name__ == "__main__":
    main()
