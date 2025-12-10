"""
RepairShopr API Client

Async HTTP client for the RepairShopr REST API with rate limiting,
retry logic, and pagination support.
"""

import asyncio
from datetime import datetime
from typing import Any, AsyncIterator

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from repairshopr_connector.models import (
    RSAsset,
    RSAssetsResponse,
    RSComment,
    RSCommentsResponse,
    RSCustomer,
    RSCustomersResponse,
    RSInvoice,
    RSInvoicesResponse,
    RSTicket,
    RSTicketsResponse,
)

logger = structlog.get_logger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for RS API.

    RepairShopr allows 180 requests/minute. We use 150 for safety margin.
    """

    def __init__(self, requests_per_minute: int = 150):
        self.requests_per_minute = requests_per_minute
        self.interval = 60.0 / requests_per_minute
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request slot is available."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            time_since_last = now - self._last_request

            if time_since_last < self.interval:
                await asyncio.sleep(self.interval - time_since_last)

            self._last_request = asyncio.get_event_loop().time()


class RepairShoprAPIError(Exception):
    """Base exception for RS API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RepairShoprRateLimitError(RepairShoprAPIError):
    """Raised when API rate limit is exceeded."""

    pass


class RepairShoprAuthError(RepairShoprAPIError):
    """Raised when authentication fails."""

    pass


class RepairShoprClient:
    """
    Async client for RepairShopr REST API.

    Features:
    - Automatic rate limiting (150 req/min default)
    - Retry with exponential backoff for transient errors
    - Pagination handling for list endpoints
    - Type-safe response parsing via Pydantic models
    """

    def __init__(
        self,
        subdomain: str,
        api_key: str,
        requests_per_minute: int = 150,
        timeout: float = 30.0,
    ):
        self.subdomain = subdomain
        self.api_key = api_key
        self.base_url = f"https://{subdomain}.repairshopr.com/api/v1"
        self.rate_limiter = RateLimiter(requests_per_minute)
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "RepairShoprClient":
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RepairShoprRateLimitError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=16),
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make a rate-limited request to the RS API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., "/tickets.json")
            params: Query parameters

        Returns:
            JSON response as dictionary
        """
        await self.rate_limiter.acquire()

        url = f"{self.base_url}{endpoint}"
        params = params or {}
        params["api_key"] = self.api_key

        logger.debug("Making API request", method=method, endpoint=endpoint)

        response = await self.client.request(method, url, params=params)

        if response.status_code == 429:
            logger.warning("Rate limit exceeded, will retry")
            raise RepairShoprRateLimitError("Rate limit exceeded", 429)

        if response.status_code == 401:
            raise RepairShoprAuthError("Invalid API key", 401)

        if response.status_code >= 400:
            raise RepairShoprAPIError(
                f"API error: {response.text}", response.status_code
            )

        return response.json()

    # -------------------------------------------------------------------------
    # Tickets
    # -------------------------------------------------------------------------

    async def get_tickets(
        self,
        page: int = 1,
        customer_id: int | None = None,
        status: str | None = None,
        number: int | None = None,
        since: datetime | None = None,
    ) -> RSTicketsResponse:
        """
        Get paginated list of tickets.

        Args:
            page: Page number (1-indexed)
            customer_id: Filter by customer
            status: Filter by status
            number: Filter by ticket number
            since: Only tickets updated after this time
        """
        params: dict[str, Any] = {"page": page}

        if customer_id:
            params["customer_id"] = customer_id
        if status:
            params["status"] = status
        if number:
            params["number"] = number
        if since:
            params["since_updated_at"] = since.isoformat()

        data = await self._request("GET", "/tickets.json", params)
        return RSTicketsResponse.model_validate(data)

    async def get_ticket(self, ticket_id: int) -> RSTicket:
        """Get a single ticket by ID."""
        data = await self._request("GET", f"/tickets/{ticket_id}")
        return RSTicket.model_validate(data.get("ticket", data))

    async def get_ticket_comments(self, ticket_id: int) -> list[RSComment]:
        """Get all comments for a ticket."""
        data = await self._request("GET", f"/tickets/{ticket_id}/comments")
        response = RSCommentsResponse.model_validate(data)
        return response.comments

    async def iter_all_tickets(
        self,
        since: datetime | None = None,
        status: str | None = None,
        include_comments: bool = True,
    ) -> AsyncIterator[RSTicket]:
        """
        Iterate through all tickets with automatic pagination.

        Args:
            since: Only tickets updated after this time
            status: Filter by status
            include_comments: Fetch comments for each ticket

        Yields:
            RSTicket objects
        """
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = await self.get_tickets(
                page=page,
                since=since,
                status=status,
            )
            total_pages = response.total_pages

            logger.info(
                "Fetched tickets page",
                page=page,
                total_pages=total_pages,
                count=len(response.tickets),
            )

            for ticket in response.tickets:
                if include_comments:
                    ticket.comments = await self.get_ticket_comments(ticket.id)
                yield ticket

            page += 1

    # -------------------------------------------------------------------------
    # Customers
    # -------------------------------------------------------------------------

    async def get_customers(
        self,
        page: int = 1,
        query: str | None = None,
        since: datetime | None = None,
    ) -> RSCustomersResponse:
        """Get paginated list of customers."""
        params: dict[str, Any] = {"page": page}

        if query:
            params["query"] = query
        if since:
            params["since_updated_at"] = since.isoformat()

        data = await self._request("GET", "/customers.json", params)
        return RSCustomersResponse.model_validate(data)

    async def get_customer(self, customer_id: int) -> RSCustomer:
        """Get a single customer by ID."""
        data = await self._request("GET", f"/customers/{customer_id}")
        return RSCustomer.model_validate(data.get("customer", data))

    async def iter_all_customers(
        self,
        since: datetime | None = None,
    ) -> AsyncIterator[RSCustomer]:
        """Iterate through all customers with automatic pagination."""
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = await self.get_customers(page=page, since=since)
            total_pages = response.total_pages

            logger.info(
                "Fetched customers page",
                page=page,
                total_pages=total_pages,
                count=len(response.customers),
            )

            for customer in response.customers:
                yield customer

            page += 1

    # -------------------------------------------------------------------------
    # Assets
    # -------------------------------------------------------------------------

    async def get_assets(
        self,
        page: int = 1,
        customer_id: int | None = None,
        asset_type_id: int | None = None,
        query: str | None = None,
        since: datetime | None = None,
    ) -> RSAssetsResponse:
        """Get paginated list of customer assets."""
        params: dict[str, Any] = {"page": page}

        if customer_id:
            params["customer_id"] = customer_id
        if asset_type_id:
            params["asset_type_id"] = asset_type_id
        if query:
            params["query"] = query
        if since:
            params["since_updated_at"] = since.isoformat()

        data = await self._request("GET", "/customer_assets.json", params)
        return RSAssetsResponse.model_validate(data)

    async def get_asset(self, asset_id: int) -> RSAsset:
        """Get a single asset by ID."""
        data = await self._request("GET", f"/customer_assets/{asset_id}")
        return RSAsset.model_validate(data.get("asset", data))

    async def iter_all_assets(
        self,
        since: datetime | None = None,
    ) -> AsyncIterator[RSAsset]:
        """Iterate through all assets with automatic pagination."""
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = await self.get_assets(page=page, since=since)
            total_pages = response.total_pages

            logger.info(
                "Fetched assets page",
                page=page,
                total_pages=total_pages,
                count=len(response.assets),
            )

            for asset in response.assets:
                yield asset

            page += 1

    # -------------------------------------------------------------------------
    # Invoices
    # -------------------------------------------------------------------------

    async def get_invoices(
        self,
        page: int = 1,
        customer_id: int | None = None,
        since: datetime | None = None,
    ) -> RSInvoicesResponse:
        """Get paginated list of invoices."""
        params: dict[str, Any] = {"page": page}

        if customer_id:
            params["customer_id"] = customer_id
        if since:
            params["since_updated_at"] = since.isoformat()

        data = await self._request("GET", "/invoices.json", params)
        return RSInvoicesResponse.model_validate(data)

    async def iter_all_invoices(
        self,
        since: datetime | None = None,
    ) -> AsyncIterator[RSInvoice]:
        """Iterate through all invoices with automatic pagination."""
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = await self.get_invoices(page=page, since=since)
            total_pages = response.total_pages

            logger.info(
                "Fetched invoices page",
                page=page,
                total_pages=total_pages,
                count=len(response.invoices),
            )

            for invoice in response.invoices:
                yield invoice

            page += 1

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    async def get_all_ticket_ids(self) -> AsyncIterator[int]:
        """
        Get only ticket IDs for slim connector pruning.

        This is more efficient than fetching full ticket data.
        """
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = await self.get_tickets(page=page)
            total_pages = response.total_pages

            for ticket in response.tickets:
                yield ticket.id

            page += 1

    async def get_all_customer_ids(self) -> AsyncIterator[int]:
        """Get only customer IDs for slim connector pruning."""
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = await self.get_customers(page=page)
            total_pages = response.total_pages

            for customer in response.customers:
                yield customer.id

            page += 1

    async def get_all_asset_ids(self) -> AsyncIterator[int]:
        """Get only asset IDs for slim connector pruning."""
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = await self.get_assets(page=page)
            total_pages = response.total_pages

            for asset in response.assets:
                yield asset.id

            page += 1
