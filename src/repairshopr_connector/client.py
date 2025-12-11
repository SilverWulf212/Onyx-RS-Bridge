"""
RepairShopr API Client - Production Grade

Synchronous HTTP client with:
- Proper rate limiting (token bucket)
- Retry with exponential backoff for transient errors (429, 5xx, network)
- Connection pooling
- Request/response logging
- Input validation
- Pagination helpers with deduplication
"""

import re
import time
from datetime import datetime, timezone
from typing import Any, Iterator

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from repairshopr_connector.rate_limiter import TokenBucketRateLimiter
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


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RepairShoprAPIError(Exception):
    """Base exception for RS API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self) -> str:
        base = super().__str__()
        if self.status_code:
            return f"{base} (HTTP {self.status_code})"
        return base


class RepairShoprRateLimitError(RepairShoprAPIError):
    """Raised when API rate limit is exceeded (429)."""
    pass


class RepairShoprAuthError(RepairShoprAPIError):
    """Raised when authentication fails (401/403)."""
    pass


class RepairShoprServerError(RepairShoprAPIError):
    """Raised on server errors (5xx) - these are retryable."""
    pass


class RepairShoprNotFoundError(RepairShoprAPIError):
    """Raised when resource not found (404)."""
    pass


# ---------------------------------------------------------------------------
# Retry Configuration
# ---------------------------------------------------------------------------

def is_retryable_error(exception: BaseException) -> bool:
    """Determine if an exception should trigger a retry."""
    if isinstance(exception, RepairShoprRateLimitError):
        return True
    if isinstance(exception, RepairShoprServerError):
        return True
    if isinstance(exception, httpx.TransportError):
        return True
    if isinstance(exception, httpx.TimeoutException):
        return True
    return False


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class RepairShoprClient:
    """
    Production-grade RepairShopr API client.

    Features:
    - Synchronous (no async/sync mixing issues)
    - Token bucket rate limiting with burst support
    - Automatic retry for transient errors (429, 5xx, network)
    - Connection pooling via httpx
    - Structured logging for observability
    - Input validation

    Example:
        client = RepairShoprClient(
            subdomain="yourcompany",
            api_key="your-key"
        )

        with client:
            for ticket in client.iter_all_tickets():
                print(ticket.number)
    """

    # Subdomain validation: alphanumeric and hyphens only
    SUBDOMAIN_PATTERN = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$')

    def __init__(
        self,
        subdomain: str,
        api_key: str,
        requests_per_minute: int = 150,
        timeout: float = 30.0,
        max_retries: int = 4,
    ):
        """
        Initialize the client.

        Args:
            subdomain: Your RS subdomain (validated for safety)
            api_key: API key from RS profile
            requests_per_minute: Rate limit (RS allows 180, default 150 for safety)
            timeout: Request timeout in seconds
            max_retries: Max retry attempts for transient errors
        """
        # Validate subdomain to prevent URL injection
        if not self.SUBDOMAIN_PATTERN.match(subdomain):
            raise ValueError(
                f"Invalid subdomain '{subdomain}'. "
                "Must be alphanumeric with optional hyphens, 1-63 characters."
            )

        if not api_key or len(api_key) < 10:
            raise ValueError("API key appears invalid (too short)")

        self.subdomain = subdomain
        self.api_key = api_key
        self.base_url = f"https://{subdomain}.repairshopr.com/api/v1"
        self.timeout = timeout
        self.max_retries = max_retries

        self.rate_limiter = TokenBucketRateLimiter(requests_per_minute=requests_per_minute)
        self._client: httpx.Client | None = None

        # Request counters for observability
        self._request_count = 0
        self._error_count = 0

        self._log = logger.bind(subdomain=subdomain)

    def __enter__(self) -> "RepairShoprClient":
        """Initialize HTTP client with connection pooling."""
        self._client = httpx.Client(
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            headers={"User-Agent": "Onyx-RS-Bridge/2.0"},
        )
        return self

    def __exit__(self, *args: Any) -> None:
        """Clean up HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    @property
    def client(self) -> httpx.Client:
        """Get HTTP client, creating if needed."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                headers={"User-Agent": "Onyx-RS-Bridge/2.0"},
            )
        return self._client

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make a rate-limited, retrying request to the RS API.

        This is the core request method with all safety features.
        """
        log = self._log.bind(endpoint=endpoint, method=method)

        @retry(
            retry=retry_if_exception(is_retryable_error),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=2, min=2, max=30),
            before_sleep=before_sleep_log(log, "INFO"),
            reraise=True,
        )
        def _do_request() -> dict[str, Any]:
            # Rate limit
            self.rate_limiter.acquire()

            url = f"{self.base_url}{endpoint}"
            request_params = params.copy() if params else {}
            request_params["api_key"] = self.api_key

            self._request_count += 1
            request_id = self._request_count

            log.debug("API request", request_id=request_id)

            start_time = time.monotonic()
            response = self.client.request(method, url, params=request_params)
            elapsed = time.monotonic() - start_time

            log.debug(
                "API response",
                request_id=request_id,
                status_code=response.status_code,
                elapsed_ms=round(elapsed * 1000),
            )

            # Handle errors by status code
            if response.status_code == 429:
                self._error_count += 1
                raise RepairShoprRateLimitError(
                    "Rate limit exceeded - will retry",
                    status_code=429,
                    response_body=response.text[:500],
                )

            if response.status_code in (401, 403):
                self._error_count += 1
                raise RepairShoprAuthError(
                    "Authentication failed - check your API key",
                    status_code=response.status_code,
                )

            if response.status_code == 404:
                self._error_count += 1
                raise RepairShoprNotFoundError(
                    f"Resource not found: {endpoint}",
                    status_code=404,
                )

            if response.status_code >= 500:
                self._error_count += 1
                raise RepairShoprServerError(
                    f"Server error {response.status_code} - will retry",
                    status_code=response.status_code,
                    response_body=response.text[:500],
                )

            if response.status_code >= 400:
                self._error_count += 1
                raise RepairShoprAPIError(
                    f"API error: {response.text[:200]}",
                    status_code=response.status_code,
                )

            # Parse JSON
            try:
                return response.json()
            except Exception as e:
                raise RepairShoprAPIError(f"Invalid JSON response: {e}")

        return _do_request()

    # -------------------------------------------------------------------------
    # Tickets
    # -------------------------------------------------------------------------

    def get_tickets(
        self,
        page: int = 1,
        per_page: int = 25,
        customer_id: int | None = None,
        status: str | None = None,
        number: int | None = None,
    ) -> RSTicketsResponse:
        """
        Get paginated list of tickets.

        Note: RS API doesn't have a native "since" filter, so we fetch
        all and filter client-side for incremental sync.
        """
        params: dict[str, Any] = {"page": page, "per_page": per_page}

        if customer_id:
            params["customer_id"] = customer_id
        if status:
            params["status"] = status
        if number:
            params["number"] = number

        data = self._make_request("GET", "/tickets.json", params)
        return RSTicketsResponse.model_validate(data)

    def get_ticket(self, ticket_id: int) -> RSTicket:
        """Get a single ticket by ID."""
        data = self._make_request("GET", f"/tickets/{ticket_id}")
        return RSTicket.model_validate(data.get("ticket", data))

    def get_ticket_comments(self, ticket_id: int) -> list[RSComment]:
        """Get all comments for a ticket."""
        try:
            data = self._make_request("GET", f"/tickets/{ticket_id}/comments")
            response = RSCommentsResponse.model_validate(data)
            return response.comments
        except RepairShoprNotFoundError:
            return []

    def iter_all_tickets(
        self,
        since: datetime | None = None,
        status: str | None = None,
        fetch_comments: bool = False,
        seen_ids: set[int] | None = None,
    ) -> Iterator[RSTicket]:
        """
        Iterate through all tickets with pagination and deduplication.

        Args:
            since: Only yield tickets updated after this time (client-side filter)
            status: Filter by status (server-side)
            fetch_comments: Whether to fetch comments for each ticket
            seen_ids: Set of already-processed IDs (for deduplication)

        Yields:
            RSTicket objects
        """
        seen = seen_ids if seen_ids is not None else set()
        page = 1

        while True:
            response = self.get_tickets(page=page, status=status)

            if not response.tickets:
                break

            for ticket in response.tickets:
                # Deduplicate (handles pagination shifts)
                if ticket.id in seen:
                    continue
                seen.add(ticket.id)

                # Client-side time filter (UTC comparison)
                if since and ticket.updated_at:
                    ticket_time = ticket.updated_at
                    if ticket_time.tzinfo is None:
                        ticket_time = ticket_time.replace(tzinfo=timezone.utc)
                    since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
                    if ticket_time <= since_utc:
                        continue

                # Fetch comments if requested
                if fetch_comments:
                    ticket.comments = self.get_ticket_comments(ticket.id)

                yield ticket

            self._log.info(
                "Fetched tickets page",
                page=page,
                total_pages=response.total_pages,
                count=len(response.tickets),
            )

            if page >= response.total_pages:
                break

            page += 1

    # -------------------------------------------------------------------------
    # Customers
    # -------------------------------------------------------------------------

    def get_customers(
        self,
        page: int = 1,
        per_page: int = 25,
        query: str | None = None,
    ) -> RSCustomersResponse:
        """Get paginated list of customers."""
        params: dict[str, Any] = {"page": page, "per_page": per_page}

        if query:
            params["query"] = query

        data = self._make_request("GET", "/customers.json", params)
        return RSCustomersResponse.model_validate(data)

    def get_customer(self, customer_id: int) -> RSCustomer:
        """Get a single customer by ID."""
        data = self._make_request("GET", f"/customers/{customer_id}")
        return RSCustomer.model_validate(data.get("customer", data))

    def iter_all_customers(
        self,
        since: datetime | None = None,
        seen_ids: set[int] | None = None,
    ) -> Iterator[RSCustomer]:
        """Iterate through all customers with pagination."""
        seen = seen_ids if seen_ids is not None else set()
        page = 1

        while True:
            response = self.get_customers(page=page)

            if not response.customers:
                break

            for customer in response.customers:
                if customer.id in seen:
                    continue
                seen.add(customer.id)

                if since and customer.updated_at:
                    cust_time = customer.updated_at
                    if cust_time.tzinfo is None:
                        cust_time = cust_time.replace(tzinfo=timezone.utc)
                    since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
                    if cust_time <= since_utc:
                        continue

                yield customer

            self._log.info(
                "Fetched customers page",
                page=page,
                total_pages=response.total_pages,
                count=len(response.customers),
            )

            if page >= response.total_pages:
                break

            page += 1

    def get_all_customers_dict(self) -> dict[int, RSCustomer]:
        """
        Fetch all customers into a lookup dictionary.

        Use this for batch enrichment instead of N+1 queries.
        """
        customers = {}
        for customer in self.iter_all_customers():
            customers[customer.id] = customer
        return customers

    # -------------------------------------------------------------------------
    # Assets
    # -------------------------------------------------------------------------

    def get_assets(
        self,
        page: int = 1,
        per_page: int = 25,
        customer_id: int | None = None,
        asset_type_id: int | None = None,
        query: str | None = None,
    ) -> RSAssetsResponse:
        """Get paginated list of customer assets."""
        params: dict[str, Any] = {"page": page, "per_page": per_page}

        if customer_id:
            params["customer_id"] = customer_id
        if asset_type_id:
            params["asset_type_id"] = asset_type_id
        if query:
            params["query"] = query

        data = self._make_request("GET", "/customer_assets.json", params)
        return RSAssetsResponse.model_validate(data)

    def get_asset(self, asset_id: int) -> RSAsset:
        """Get a single asset by ID."""
        data = self._make_request("GET", f"/customer_assets/{asset_id}")
        return RSAsset.model_validate(data.get("asset", data))

    def iter_all_assets(
        self,
        since: datetime | None = None,
        seen_ids: set[int] | None = None,
    ) -> Iterator[RSAsset]:
        """Iterate through all assets with pagination."""
        seen = seen_ids if seen_ids is not None else set()
        page = 1

        while True:
            response = self.get_assets(page=page)

            if not response.assets:
                break

            for asset in response.assets:
                if asset.id in seen:
                    continue
                seen.add(asset.id)

                if since and asset.updated_at:
                    asset_time = asset.updated_at
                    if asset_time.tzinfo is None:
                        asset_time = asset_time.replace(tzinfo=timezone.utc)
                    since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
                    if asset_time <= since_utc:
                        continue

                yield asset

            self._log.info(
                "Fetched assets page",
                page=page,
                total_pages=response.total_pages,
                count=len(response.assets),
            )

            if page >= response.total_pages:
                break

            page += 1

    def get_all_assets_dict(self) -> dict[int, RSAsset]:
        """Fetch all assets into a lookup dictionary."""
        assets = {}
        for asset in self.iter_all_assets():
            assets[asset.id] = asset
        return assets

    def get_assets_by_customer(self) -> dict[int, list[RSAsset]]:
        """Fetch all assets grouped by customer ID."""
        by_customer: dict[int, list[RSAsset]] = {}
        for asset in self.iter_all_assets():
            if asset.customer_id:
                by_customer.setdefault(asset.customer_id, []).append(asset)
        return by_customer

    # -------------------------------------------------------------------------
    # Invoices
    # -------------------------------------------------------------------------

    def get_invoices(
        self,
        page: int = 1,
        per_page: int = 25,
        customer_id: int | None = None,
    ) -> RSInvoicesResponse:
        """Get paginated list of invoices."""
        params: dict[str, Any] = {"page": page, "per_page": per_page}

        if customer_id:
            params["customer_id"] = customer_id

        data = self._make_request("GET", "/invoices.json", params)
        return RSInvoicesResponse.model_validate(data)

    def iter_all_invoices(
        self,
        since: datetime | None = None,
        seen_ids: set[int] | None = None,
    ) -> Iterator[RSInvoice]:
        """Iterate through all invoices with pagination."""
        seen = seen_ids if seen_ids is not None else set()
        page = 1

        while True:
            response = self.get_invoices(page=page)

            if not response.invoices:
                break

            for invoice in response.invoices:
                if invoice.id in seen:
                    continue
                seen.add(invoice.id)

                if since and invoice.updated_at:
                    inv_time = invoice.updated_at
                    if inv_time.tzinfo is None:
                        inv_time = inv_time.replace(tzinfo=timezone.utc)
                    since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
                    if inv_time <= since_utc:
                        continue

                yield invoice

            self._log.info(
                "Fetched invoices page",
                page=page,
                total_pages=response.total_pages,
                count=len(response.invoices),
            )

            if page >= response.total_pages:
                break

            page += 1

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get client statistics for monitoring."""
        return {
            "subdomain": self.subdomain,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": round(self._error_count / max(1, self._request_count), 4),
            "rate_limiter": self.rate_limiter.get_stats(),
        }

    def health_check(self) -> dict[str, Any]:
        """Verify API connectivity and credentials."""
        try:
            data = self._make_request("GET", "/me")
            return {
                "status": "healthy",
                "user": data.get("user", {}).get("email", "unknown"),
                "subdomain": self.subdomain,
            }
        except RepairShoprAuthError:
            return {"status": "auth_error", "message": "Invalid API key"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
