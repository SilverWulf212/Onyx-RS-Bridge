"""
Pytest configuration and fixtures for RepairShopr connector tests.
"""

import pytest
from datetime import datetime, timezone


@pytest.fixture
def sample_ticket_data():
    """Sample ticket data from RS API."""
    return {
        "id": 12345,
        "number": 1001,
        "subject": "Laptop won't boot - blue screen error",
        "status": "In Progress",
        "problem_type": "Hardware",
        "priority": "High",
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-16T14:20:00Z",
        "customer_id": 5001,
        "customer_business_then_name": "Acme Corporation",
        "user_id": 101,
        "problem_type_description": "Customer reports laptop shows blue screen on startup. Started after Windows update.",
        "resolution": None,
        "comments": [],
        "line_items": [],
    }


@pytest.fixture
def sample_customer_data():
    """Sample customer data from RS API."""
    return {
        "id": 5001,
        "business_name": "Acme Corporation",
        "firstname": "John",
        "lastname": "Smith",
        "email": "john.smith@acme.com",
        "phone": "555-123-4567",
        "mobile": "555-987-6543",
        "address": "123 Main Street",
        "address_2": "Suite 100",
        "city": "Springfield",
        "state": "IL",
        "zip": "62701",
        "notes": "VIP customer - priority support",
        "created_at": "2023-06-01T09:00:00Z",
        "updated_at": "2024-01-10T11:30:00Z",
        "get_sms": True,
        "opt_out": False,
        "no_email": False,
    }


@pytest.fixture
def sample_asset_data():
    """Sample asset data from RS API."""
    return {
        "id": 8001,
        "name": "Dell Latitude 5520",
        "customer_id": 5001,
        "asset_serial": "ABC123XYZ",
        "asset_type_id": 1,
        "asset_type_name": "Laptop",
        "properties": {
            "Manufacturer": "Dell",
            "Model": "Latitude 5520",
            "Operating System": "Windows 11 Pro",
            "RAM": "16GB",
            "Storage": "512GB SSD",
        },
        "created_at": "2023-08-15T14:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z",
    }


@pytest.fixture
def sample_comment_data():
    """Sample comment data from RS API."""
    return {
        "id": 99001,
        "ticket_id": 12345,
        "subject": "Initial diagnosis",
        "body": "Ran diagnostics. RAM test passed. Suspecting corrupted Windows update. Will try system restore.",
        "tech": "Mike Technician",
        "hidden": False,
        "created_at": "2024-01-15T11:00:00Z",
        "updated_at": "2024-01-15T11:00:00Z",
    }


@pytest.fixture
def sample_tickets_response(sample_ticket_data):
    """Sample paginated tickets response."""
    return {
        "tickets": [sample_ticket_data],
        "page": 1,
        "total_pages": 1,
        "total_entries": 1,
    }


@pytest.fixture
def sample_customers_response(sample_customer_data):
    """Sample paginated customers response."""
    return {
        "customers": [sample_customer_data],
        "page": 1,
        "total_pages": 1,
        "total_entries": 1,
    }


@pytest.fixture
def sample_assets_response(sample_asset_data):
    """Sample paginated assets response."""
    return {
        "assets": [sample_asset_data],
        "page": 1,
        "total_pages": 1,
        "total_entries": 1,
    }
