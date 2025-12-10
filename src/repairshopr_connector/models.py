"""
Pydantic models for RepairShopr API responses.

These models provide type-safe parsing of RS API data and serve as the
intermediate representation before conversion to Onyx Documents.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RSContact(BaseModel):
    """Contact associated with a customer."""

    id: int
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    customer_id: int | None = None


class RSCustomer(BaseModel):
    """RepairShopr customer entity."""

    id: int
    business_name: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    address: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Preferences
    get_sms: bool = False
    opt_out: bool = False
    no_email: bool = False

    # Related data
    contacts: list[RSContact] = Field(default_factory=list)

    @property
    def full_name(self) -> str:
        """Get full name, preferring business name."""
        if self.business_name:
            return self.business_name
        parts = [p for p in [self.firstname, self.lastname] if p]
        return " ".join(parts) if parts else f"Customer #{self.id}"

    @property
    def full_address(self) -> str:
        """Format complete address."""
        parts = [
            self.address,
            self.address_2,
            ", ".join(filter(None, [self.city, self.state, self.zip])),
        ]
        return "\n".join(filter(None, parts))


class RSAsset(BaseModel):
    """RepairShopr customer asset (device/equipment)."""

    id: int
    name: str
    customer_id: int | None = None
    asset_serial: str | None = None
    asset_type_id: int | None = None
    asset_type_name: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Common asset properties (extracted from properties dict)
    @property
    def manufacturer(self) -> str | None:
        return self.properties.get("manufacturer") or self.properties.get("Manufacturer")

    @property
    def model(self) -> str | None:
        return self.properties.get("model") or self.properties.get("Model")

    @property
    def operating_system(self) -> str | None:
        return self.properties.get("os") or self.properties.get("Operating System")


class RSLineItem(BaseModel):
    """Line item on a ticket or invoice."""

    id: int | None = None
    name: str
    quantity: float = 1.0
    price: float = 0.0
    cost: float = 0.0
    taxable: bool = False
    item: str | None = None  # SKU or item code

    @property
    def total(self) -> float:
        return self.quantity * self.price


class RSComment(BaseModel):
    """Comment/update on a ticket."""

    id: int
    ticket_id: int
    subject: str | None = None
    body: str | None = None
    tech: str | None = None
    hidden: bool = False
    do_not_email: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_internal(self) -> bool:
        """Check if this is an internal/private comment."""
        return self.hidden


class RSTicket(BaseModel):
    """RepairShopr ticket entity - the primary document type."""

    id: int
    number: int
    subject: str
    status: str = "New"
    problem_type: str | None = None
    priority: str | None = None

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None
    due_date: datetime | None = None
    resolved_at: datetime | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None

    # Relationships
    customer_id: int | None = None
    customer_business_then_name: str | None = None
    user_id: int | None = None  # Assigned technician
    location_id: int | None = None

    # Content
    problem_description: str | None = Field(None, alias="problem_type_description")
    resolution: str | None = None

    # Related data (populated via additional API calls)
    comments: list[RSComment] = Field(default_factory=list)
    line_items: list[RSLineItem] = Field(default_factory=list)
    assets: list[RSAsset] = Field(default_factory=list)

    # Metadata
    properties: dict[str, Any] = Field(default_factory=dict)
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    # Computed/lookup fields (populated during enrichment)
    customer: RSCustomer | None = None
    assigned_tech_name: str | None = None
    location_name: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> str:
        """Normalize status values."""
        if v is None:
            return "New"
        return str(v).strip()

    @property
    def is_resolved(self) -> bool:
        """Check if ticket is resolved/closed."""
        return self.status.lower() in ["resolved", "closed", "completed", "invoiced"]

    @property
    def is_open(self) -> bool:
        """Check if ticket is still open."""
        return not self.is_resolved

    @property
    def public_comments(self) -> list[RSComment]:
        """Get non-hidden comments."""
        return [c for c in self.comments if not c.hidden]

    @property
    def internal_comments(self) -> list[RSComment]:
        """Get hidden/internal comments."""
        return [c for c in self.comments if c.hidden]

    @property
    def total_parts_cost(self) -> float:
        """Calculate total cost of parts/items."""
        return sum(item.total for item in self.line_items)


class RSInvoice(BaseModel):
    """RepairShopr invoice entity."""

    id: int
    number: str
    customer_id: int | None = None
    ticket_id: int | None = None
    date: datetime | None = None
    date_received: datetime | None = None
    paid: bool = False
    total: float = 0.0
    balance_due: float = 0.0
    location_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    line_items: list[RSLineItem] = Field(default_factory=list)


class RSAppointment(BaseModel):
    """RepairShopr appointment entity."""

    id: int
    start_at: datetime | None = None
    end_at: datetime | None = None
    customer_id: int | None = None
    ticket_id: int | None = None
    user_id: int | None = None
    title: str | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# API Response wrappers


class RSPaginatedResponse(BaseModel):
    """Generic paginated response from RS API."""

    page: int = 1
    total_pages: int = 1
    total_entries: int = 0


class RSTicketsResponse(RSPaginatedResponse):
    """Response from GET /tickets.json"""

    tickets: list[RSTicket] = Field(default_factory=list)


class RSCustomersResponse(RSPaginatedResponse):
    """Response from GET /customers.json"""

    customers: list[RSCustomer] = Field(default_factory=list)


class RSAssetsResponse(RSPaginatedResponse):
    """Response from GET /customer_assets.json"""

    assets: list[RSAsset] = Field(default_factory=list)


class RSInvoicesResponse(RSPaginatedResponse):
    """Response from GET /invoices.json"""

    invoices: list[RSInvoice] = Field(default_factory=list)


class RSCommentsResponse(BaseModel):
    """Response from GET /tickets/:id/comments"""

    comments: list[RSComment] = Field(default_factory=list)
