"""
Tests for RepairShopr Document Builder.
"""

import pytest

from repairshopr_connector.document_builder import (
    RepairShoprDocumentBuilder,
    DOC_PREFIX_TICKET,
    DOC_PREFIX_CUSTOMER,
    DOC_PREFIX_ASSET,
    DOCUMENT_SOURCE,
)
from repairshopr_connector.models import RSTicket, RSCustomer, RSAsset, RSComment


class TestRepairShoprDocumentBuilder:
    """Tests for document builder."""

    @pytest.fixture
    def builder(self):
        """Create a document builder instance."""
        return RepairShoprDocumentBuilder(subdomain="testshop")

    @pytest.fixture
    def ticket(self, sample_ticket_data, sample_comment_data):
        """Create a ticket with comments."""
        sample_ticket_data["comments"] = [sample_comment_data]
        return RSTicket.model_validate(sample_ticket_data)

    @pytest.fixture
    def customer(self, sample_customer_data):
        """Create a customer."""
        return RSCustomer.model_validate(sample_customer_data)

    @pytest.fixture
    def asset(self, sample_asset_data):
        """Create an asset."""
        return RSAsset.model_validate(sample_asset_data)

    def test_build_ticket_document(self, builder, ticket, customer, asset):
        """Test building a ticket document."""
        doc = builder.build_ticket_document(ticket, customer, asset)

        # Check ID format
        assert doc.id == f"{DOC_PREFIX_TICKET}12345"

        # Check source
        assert doc.source == DOCUMENT_SOURCE

        # Check semantic identifier
        assert "Ticket #1001" in doc.semantic_identifier
        assert "Laptop won't boot" in doc.semantic_identifier

        # Check content includes key information
        content = doc.sections[0].text
        assert "TICKET #1001" in content
        assert "In Progress" in content
        assert "Hardware" in content
        assert "Acme Corporation" in content
        assert "blue screen" in content.lower()

        # Check metadata
        assert doc.metadata["ticket_number"] == 1001
        assert doc.metadata["status"] == "In Progress"
        assert doc.metadata["customer_name"] == "Acme Corporation"

        # Check link
        assert "testshop.repairshopr.com/tickets/12345" in doc.sections[0].link

    def test_build_ticket_document_with_comments(self, builder, ticket, customer, asset):
        """Test that comments are included in ticket document."""
        doc = builder.build_ticket_document(ticket, customer, asset)
        content = doc.sections[0].text

        assert "Initial diagnosis" in content
        assert "Mike Technician" in content
        assert "RAM test passed" in content

    def test_build_customer_document(self, builder, customer):
        """Test building a customer document."""
        doc = builder.build_customer_document(customer)

        # Check ID format
        assert doc.id == f"{DOC_PREFIX_CUSTOMER}5001"

        # Check semantic identifier
        assert "Customer:" in doc.semantic_identifier
        assert "Acme Corporation" in doc.semantic_identifier

        # Check content
        content = doc.sections[0].text
        assert "Acme Corporation" in content
        assert "john.smith@acme.com" in content
        assert "555-123-4567" in content
        assert "VIP customer" in content

        # Check metadata
        assert doc.metadata["customer_id"] == 5001
        assert doc.metadata["email"] == "john.smith@acme.com"

    def test_build_asset_document(self, builder, asset, customer):
        """Test building an asset document."""
        doc = builder.build_asset_document(asset, customer)

        # Check ID format
        assert doc.id == f"{DOC_PREFIX_ASSET}8001"

        # Check semantic identifier
        assert "Asset:" in doc.semantic_identifier
        assert "Dell Latitude 5520" in doc.semantic_identifier
        assert "ABC123XYZ" in doc.semantic_identifier

        # Check content
        content = doc.sections[0].text
        assert "Dell Latitude 5520" in content
        assert "ABC123XYZ" in content
        assert "Laptop" in content
        assert "Dell" in content
        assert "Windows 11 Pro" in content

        # Check metadata
        assert doc.metadata["asset_serial"] == "ABC123XYZ"
        assert doc.metadata["manufacturer"] == "Dell"

    def test_document_urls(self, builder, ticket, customer, asset):
        """Test that document URLs are correct."""
        ticket_doc = builder.build_ticket_document(ticket)
        customer_doc = builder.build_customer_document(customer)
        asset_doc = builder.build_asset_document(asset)

        assert ticket_doc.sections[0].link == "https://testshop.repairshopr.com/tickets/12345"
        assert customer_doc.sections[0].link == "https://testshop.repairshopr.com/customers/5001"
        assert asset_doc.sections[0].link == "https://testshop.repairshopr.com/customer_assets/8001"

    def test_ticket_without_customer(self, builder, ticket):
        """Test building ticket document without customer data."""
        doc = builder.build_ticket_document(ticket, customer=None, asset=None)

        # Should still have customer name from ticket data
        assert doc.metadata["customer_name"] == "Acme Corporation"

    def test_ticket_updated_at(self, builder, ticket):
        """Test that document updated_at matches ticket."""
        doc = builder.build_ticket_document(ticket)

        assert doc.doc_updated_at == ticket.updated_at
