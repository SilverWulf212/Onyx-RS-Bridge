"""
Tests for RepairShopr Pydantic models.
"""

import pytest
from datetime import datetime

from repairshopr_connector.models import (
    RSTicket,
    RSCustomer,
    RSAsset,
    RSComment,
    RSTicketsResponse,
    RSCustomersResponse,
)


class TestRSTicket:
    """Tests for RSTicket model."""

    def test_parse_ticket(self, sample_ticket_data):
        """Test parsing a ticket from API response."""
        ticket = RSTicket.model_validate(sample_ticket_data)

        assert ticket.id == 12345
        assert ticket.number == 1001
        assert ticket.subject == "Laptop won't boot - blue screen error"
        assert ticket.status == "In Progress"
        assert ticket.problem_type == "Hardware"
        assert ticket.customer_id == 5001

    def test_is_resolved_false(self, sample_ticket_data):
        """Test is_resolved property for open ticket."""
        ticket = RSTicket.model_validate(sample_ticket_data)
        assert ticket.is_resolved is False
        assert ticket.is_open is True

    def test_is_resolved_true(self, sample_ticket_data):
        """Test is_resolved property for closed ticket."""
        sample_ticket_data["status"] = "Resolved"
        ticket = RSTicket.model_validate(sample_ticket_data)
        assert ticket.is_resolved is True
        assert ticket.is_open is False

    def test_status_normalization(self, sample_ticket_data):
        """Test status normalization."""
        sample_ticket_data["status"] = "  New  "
        ticket = RSTicket.model_validate(sample_ticket_data)
        assert ticket.status == "New"

    def test_default_status(self, sample_ticket_data):
        """Test default status when None."""
        sample_ticket_data["status"] = None
        ticket = RSTicket.model_validate(sample_ticket_data)
        assert ticket.status == "New"


class TestRSCustomer:
    """Tests for RSCustomer model."""

    def test_parse_customer(self, sample_customer_data):
        """Test parsing a customer from API response."""
        customer = RSCustomer.model_validate(sample_customer_data)

        assert customer.id == 5001
        assert customer.business_name == "Acme Corporation"
        assert customer.firstname == "John"
        assert customer.lastname == "Smith"
        assert customer.email == "john.smith@acme.com"

    def test_full_name_business(self, sample_customer_data):
        """Test full_name returns business name when available."""
        customer = RSCustomer.model_validate(sample_customer_data)
        assert customer.full_name == "Acme Corporation"

    def test_full_name_individual(self, sample_customer_data):
        """Test full_name returns person name when no business."""
        sample_customer_data["business_name"] = None
        customer = RSCustomer.model_validate(sample_customer_data)
        assert customer.full_name == "John Smith"

    def test_full_address(self, sample_customer_data):
        """Test full_address formatting."""
        customer = RSCustomer.model_validate(sample_customer_data)
        address = customer.full_address
        assert "123 Main Street" in address
        assert "Suite 100" in address
        assert "Springfield" in address
        assert "IL" in address


class TestRSAsset:
    """Tests for RSAsset model."""

    def test_parse_asset(self, sample_asset_data):
        """Test parsing an asset from API response."""
        asset = RSAsset.model_validate(sample_asset_data)

        assert asset.id == 8001
        assert asset.name == "Dell Latitude 5520"
        assert asset.asset_serial == "ABC123XYZ"
        assert asset.customer_id == 5001

    def test_asset_properties(self, sample_asset_data):
        """Test extracting properties from asset."""
        asset = RSAsset.model_validate(sample_asset_data)

        assert asset.manufacturer == "Dell"
        assert asset.model == "Latitude 5520"
        assert asset.operating_system == "Windows 11 Pro"


class TestRSComment:
    """Tests for RSComment model."""

    def test_parse_comment(self, sample_comment_data):
        """Test parsing a comment from API response."""
        comment = RSComment.model_validate(sample_comment_data)

        assert comment.id == 99001
        assert comment.ticket_id == 12345
        assert comment.tech == "Mike Technician"
        assert comment.hidden is False

    def test_is_internal(self, sample_comment_data):
        """Test is_internal property."""
        comment = RSComment.model_validate(sample_comment_data)
        assert comment.is_internal is False

        sample_comment_data["hidden"] = True
        hidden_comment = RSComment.model_validate(sample_comment_data)
        assert hidden_comment.is_internal is True


class TestPaginatedResponses:
    """Tests for paginated response models."""

    def test_tickets_response(self, sample_tickets_response):
        """Test parsing tickets response."""
        response = RSTicketsResponse.model_validate(sample_tickets_response)

        assert response.page == 1
        assert response.total_pages == 1
        assert response.total_entries == 1
        assert len(response.tickets) == 1
        assert response.tickets[0].number == 1001

    def test_customers_response(self, sample_customers_response):
        """Test parsing customers response."""
        response = RSCustomersResponse.model_validate(sample_customers_response)

        assert response.page == 1
        assert len(response.customers) == 1
        assert response.customers[0].id == 5001
