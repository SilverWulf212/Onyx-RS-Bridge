"""
Document Builder for RepairShopr Entities

Converts RepairShopr API models into Onyx Document format for indexing.
Each entity type (ticket, customer, asset) gets rich, searchable content.
"""

from datetime import datetime, timezone
from typing import Any

from repairshopr_connector.models import (
    RSAsset,
    RSComment,
    RSCustomer,
    RSInvoice,
    RSTicket,
)


# Document type prefixes for unique IDs
DOC_PREFIX_TICKET = "rs_ticket_"
DOC_PREFIX_CUSTOMER = "rs_customer_"
DOC_PREFIX_ASSET = "rs_asset_"
DOC_PREFIX_INVOICE = "rs_invoice_"

# Source identifier for Onyx
DOCUMENT_SOURCE = "REPAIRSHOPR"


class DocumentSection:
    """
    Represents a section of content in an Onyx document.

    Matches Onyx's Section model structure.
    """

    def __init__(self, link: str, text: str):
        self.link = link
        self.text = text

    def to_dict(self) -> dict[str, str]:
        return {"link": self.link, "text": self.text}


class BasicExpertInfo:
    """
    Represents a document owner/expert.

    Matches Onyx's BasicExpertInfo model.
    """

    def __init__(self, display_name: str, email: str | None = None):
        self.display_name = display_name
        self.email = email

    def to_dict(self) -> dict[str, str | None]:
        return {"display_name": self.display_name, "email": self.email}


class OnyxDocument:
    """
    Document structure compatible with Onyx's Document model.

    This is the output format that gets sent to Onyx for indexing.
    """

    def __init__(
        self,
        id: str,
        sections: list[DocumentSection],
        source: str,
        semantic_identifier: str,
        metadata: dict[str, Any],
        doc_updated_at: datetime | None = None,
        primary_owners: list[BasicExpertInfo] | None = None,
        secondary_owners: list[BasicExpertInfo] | None = None,
        title: str | None = None,
    ):
        self.id = id
        self.sections = sections
        self.source = source
        self.semantic_identifier = semantic_identifier
        self.metadata = metadata
        self.doc_updated_at = doc_updated_at or datetime.now(timezone.utc)
        self.primary_owners = primary_owners or []
        self.secondary_owners = secondary_owners or []
        self.title = title

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "sections": [s.to_dict() for s in self.sections],
            "source": self.source,
            "semantic_identifier": self.semantic_identifier,
            "metadata": self.metadata,
            "doc_updated_at": self.doc_updated_at.isoformat() if self.doc_updated_at else None,
            "primary_owners": [o.to_dict() for o in self.primary_owners],
            "secondary_owners": [o.to_dict() for o in self.secondary_owners],
            "title": self.title,
        }


class RepairShoprDocumentBuilder:
    """
    Builds Onyx documents from RepairShopr entities.

    Creates rich, searchable content that preserves context and
    relationships between entities.
    """

    def __init__(self, subdomain: str):
        self.subdomain = subdomain
        self.base_url = f"https://{subdomain}.repairshopr.com"

    def _ticket_url(self, ticket_id: int) -> str:
        return f"{self.base_url}/tickets/{ticket_id}"

    def _customer_url(self, customer_id: int) -> str:
        return f"{self.base_url}/customers/{customer_id}"

    def _asset_url(self, asset_id: int) -> str:
        return f"{self.base_url}/customer_assets/{asset_id}"

    def _invoice_url(self, invoice_id: int) -> str:
        return f"{self.base_url}/invoices/{invoice_id}"

    def _format_comments(self, comments: list[RSComment], include_internal: bool = True) -> str:
        """Format ticket comments into readable text."""
        if not comments:
            return "No comments recorded."

        lines = []
        for comment in sorted(comments, key=lambda c: c.created_at or datetime.min):
            if comment.hidden and not include_internal:
                continue

            visibility = "[INTERNAL] " if comment.hidden else ""
            tech = comment.tech or "System"
            date = comment.created_at.strftime("%Y-%m-%d %H:%M") if comment.created_at else "N/A"

            lines.append(f"--- {visibility}{date} by {tech} ---")
            if comment.subject:
                lines.append(f"Subject: {comment.subject}")
            if comment.body:
                lines.append(comment.body)
            lines.append("")

        return "\n".join(lines) if lines else "No comments recorded."

    def _format_line_items(self, items: list) -> str:
        """Format line items (parts, labor) into readable text."""
        if not items:
            return "No parts or labor recorded."

        lines = []
        total = 0.0
        for item in items:
            qty = item.quantity
            name = item.name
            price = item.price
            item_total = qty * price
            total += item_total
            lines.append(f"  - {qty}x {name} @ ${price:.2f} = ${item_total:.2f}")

        lines.append(f"  TOTAL: ${total:.2f}")
        return "\n".join(lines)

    def build_ticket_document(
        self,
        ticket: RSTicket,
        customer: RSCustomer | None = None,
        asset: RSAsset | None = None,
    ) -> OnyxDocument:
        """
        Build an Onyx document from a RepairShopr ticket.

        Creates rich, searchable content including:
        - Ticket details and status
        - Customer information
        - Asset/device information
        - Problem description and resolution
        - Full comment history
        - Parts and labor used
        """
        # Build the semantic identifier (title shown in search results)
        semantic_id = f"Ticket #{ticket.number}: {ticket.subject}"

        # Customer name for display
        customer_name = "Unknown Customer"
        if customer:
            customer_name = customer.full_name
        elif ticket.customer_business_then_name:
            customer_name = ticket.customer_business_then_name

        # Asset info
        asset_info = "No asset linked"
        if asset:
            asset_info = f"{asset.name}"
            if asset.asset_serial:
                asset_info += f" (Serial: {asset.asset_serial})"
            if asset.manufacturer or asset.model:
                asset_info += f" - {asset.manufacturer or ''} {asset.model or ''}".strip()

        # Build the main searchable content
        content_parts = [
            f"REPAIRSHOPR TICKET #{ticket.number}",
            f"{'=' * 50}",
            "",
            f"SUBJECT: {ticket.subject}",
            f"STATUS: {ticket.status}",
            f"PROBLEM TYPE: {ticket.problem_type or 'Not specified'}",
            f"PRIORITY: {ticket.priority or 'Normal'}",
            "",
            f"CUSTOMER: {customer_name}",
            f"ASSET/DEVICE: {asset_info}",
            f"ASSIGNED TO: {ticket.assigned_tech_name or 'Unassigned'}",
            f"LOCATION: {ticket.location_name or 'Default'}",
            "",
            f"CREATED: {ticket.created_at.strftime('%Y-%m-%d %H:%M') if ticket.created_at else 'N/A'}",
            f"DUE DATE: {ticket.due_date.strftime('%Y-%m-%d') if ticket.due_date else 'Not set'}",
            f"RESOLVED: {ticket.resolved_at.strftime('%Y-%m-%d %H:%M') if ticket.resolved_at else 'Not yet'}",
            "",
            "PROBLEM DESCRIPTION:",
            "-" * 30,
            ticket.problem_description or "No description provided.",
            "",
            "RESOLUTION/NOTES:",
            "-" * 30,
            ticket.resolution or "No resolution recorded yet.",
            "",
            "WORK HISTORY / COMMENTS:",
            "-" * 30,
            self._format_comments(ticket.comments),
            "",
            "PARTS & LABOR:",
            "-" * 30,
            self._format_line_items(ticket.line_items),
        ]

        # Add customer context if available
        if customer:
            content_parts.extend([
                "",
                "CUSTOMER DETAILS:",
                "-" * 30,
                f"Name: {customer.full_name}",
                f"Email: {customer.email or 'N/A'}",
                f"Phone: {customer.phone or customer.mobile or 'N/A'}",
                f"Address: {customer.full_address or 'N/A'}",
                f"Notes: {customer.notes or 'None'}",
            ])

        # Add asset context if available
        if asset:
            content_parts.extend([
                "",
                "ASSET DETAILS:",
                "-" * 30,
                f"Name: {asset.name}",
                f"Type: {asset.asset_type_name or 'Unknown'}",
                f"Serial: {asset.asset_serial or 'N/A'}",
                f"Manufacturer: {asset.manufacturer or 'N/A'}",
                f"Model: {asset.model or 'N/A'}",
                f"OS: {asset.operating_system or 'N/A'}",
            ])

        content = "\n".join(content_parts)

        # Build metadata for filtering
        metadata: dict[str, Any] = {
            "ticket_number": ticket.number,
            "status": ticket.status,
            "problem_type": ticket.problem_type,
            "priority": ticket.priority,
            "is_resolved": ticket.is_resolved,
            "customer_id": ticket.customer_id,
            "customer_name": customer_name,
            "technician": ticket.assigned_tech_name,
            "location": ticket.location_name,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            "comment_count": len(ticket.comments),
            "parts_count": len(ticket.line_items),
        }

        if asset:
            metadata.update({
                "asset_id": asset.id,
                "asset_name": asset.name,
                "asset_serial": asset.asset_serial,
                "asset_type": asset.asset_type_name,
            })

        # Build owners
        primary_owners = []
        if ticket.assigned_tech_name:
            primary_owners.append(BasicExpertInfo(ticket.assigned_tech_name))

        secondary_owners = []
        if customer_name != "Unknown Customer":
            secondary_owners.append(BasicExpertInfo(customer_name, customer.email if customer else None))

        return OnyxDocument(
            id=f"{DOC_PREFIX_TICKET}{ticket.id}",
            sections=[DocumentSection(self._ticket_url(ticket.id), content)],
            source=DOCUMENT_SOURCE,
            semantic_identifier=semantic_id,
            metadata=metadata,
            doc_updated_at=ticket.updated_at,
            primary_owners=primary_owners,
            secondary_owners=secondary_owners,
            title=semantic_id,
        )

    def build_customer_document(self, customer: RSCustomer) -> OnyxDocument:
        """
        Build an Onyx document from a RepairShopr customer.

        Creates searchable customer profile including contact info and notes.
        """
        semantic_id = f"Customer: {customer.full_name}"

        content_parts = [
            f"REPAIRSHOPR CUSTOMER PROFILE",
            f"{'=' * 50}",
            "",
            f"NAME: {customer.full_name}",
            f"BUSINESS: {customer.business_name or 'Individual'}",
            "",
            "CONTACT INFORMATION:",
            "-" * 30,
            f"Email: {customer.email or 'Not provided'}",
            f"Phone: {customer.phone or 'Not provided'}",
            f"Mobile: {customer.mobile or 'Not provided'}",
            "",
            "ADDRESS:",
            "-" * 30,
            customer.full_address or "No address on file",
            "",
            "NOTES:",
            "-" * 30,
            customer.notes or "No notes recorded.",
            "",
            "PREFERENCES:",
            "-" * 30,
            f"SMS Notifications: {'Enabled' if customer.get_sms else 'Disabled'}",
            f"Email Opt-Out: {'Yes' if customer.opt_out else 'No'}",
        ]

        # Add contacts if available
        if customer.contacts:
            content_parts.extend([
                "",
                "ADDITIONAL CONTACTS:",
                "-" * 30,
            ])
            for contact in customer.contacts:
                content_parts.append(
                    f"  - {contact.name or 'Unnamed'}: {contact.email or ''} {contact.phone or ''}"
                )

        content = "\n".join(content_parts)

        metadata: dict[str, Any] = {
            "customer_id": customer.id,
            "customer_name": customer.full_name,
            "business_name": customer.business_name,
            "email": customer.email,
            "phone": customer.phone or customer.mobile,
            "city": customer.city,
            "state": customer.state,
            "created_at": customer.created_at.isoformat() if customer.created_at else None,
        }

        secondary_owners = []
        if customer.full_name:
            secondary_owners.append(BasicExpertInfo(customer.full_name, customer.email))

        return OnyxDocument(
            id=f"{DOC_PREFIX_CUSTOMER}{customer.id}",
            sections=[DocumentSection(self._customer_url(customer.id), content)],
            source=DOCUMENT_SOURCE,
            semantic_identifier=semantic_id,
            metadata=metadata,
            doc_updated_at=customer.updated_at,
            secondary_owners=secondary_owners,
            title=semantic_id,
        )

    def build_asset_document(
        self,
        asset: RSAsset,
        customer: RSCustomer | None = None,
    ) -> OnyxDocument:
        """
        Build an Onyx document from a RepairShopr asset.

        Creates searchable device profile including specs and owner info.
        """
        semantic_id = f"Asset: {asset.name}"
        if asset.asset_serial:
            semantic_id += f" ({asset.asset_serial})"

        customer_name = "Unknown Owner"
        if customer:
            customer_name = customer.full_name

        content_parts = [
            f"REPAIRSHOPR ASSET/DEVICE",
            f"{'=' * 50}",
            "",
            f"NAME: {asset.name}",
            f"TYPE: {asset.asset_type_name or 'Unknown'}",
            f"SERIAL NUMBER: {asset.asset_serial or 'N/A'}",
            "",
            "SPECIFICATIONS:",
            "-" * 30,
            f"Manufacturer: {asset.manufacturer or 'N/A'}",
            f"Model: {asset.model or 'N/A'}",
            f"Operating System: {asset.operating_system or 'N/A'}",
            "",
            "OWNER:",
            "-" * 30,
            f"Customer: {customer_name}",
            "",
            f"CREATED: {asset.created_at.strftime('%Y-%m-%d') if asset.created_at else 'N/A'}",
        ]

        # Add any additional properties
        if asset.properties:
            content_parts.extend([
                "",
                "ADDITIONAL PROPERTIES:",
                "-" * 30,
            ])
            for key, value in asset.properties.items():
                if value and key.lower() not in ["manufacturer", "model", "os", "operating system"]:
                    content_parts.append(f"  {key}: {value}")

        content = "\n".join(content_parts)

        metadata: dict[str, Any] = {
            "asset_id": asset.id,
            "asset_name": asset.name,
            "asset_serial": asset.asset_serial,
            "asset_type": asset.asset_type_name,
            "customer_id": asset.customer_id,
            "customer_name": customer_name,
            "manufacturer": asset.manufacturer,
            "model": asset.model,
            "created_at": asset.created_at.isoformat() if asset.created_at else None,
        }

        secondary_owners = []
        if customer_name != "Unknown Owner":
            secondary_owners.append(BasicExpertInfo(customer_name))

        return OnyxDocument(
            id=f"{DOC_PREFIX_ASSET}{asset.id}",
            sections=[DocumentSection(self._asset_url(asset.id), content)],
            source=DOCUMENT_SOURCE,
            semantic_identifier=semantic_id,
            metadata=metadata,
            doc_updated_at=asset.updated_at,
            secondary_owners=secondary_owners,
            title=semantic_id,
        )

    def build_invoice_document(
        self,
        invoice: RSInvoice,
        customer: RSCustomer | None = None,
    ) -> OnyxDocument:
        """
        Build an Onyx document from a RepairShopr invoice.
        """
        semantic_id = f"Invoice #{invoice.number}"

        customer_name = "Unknown Customer"
        if customer:
            customer_name = customer.full_name

        content_parts = [
            f"REPAIRSHOPR INVOICE",
            f"{'=' * 50}",
            "",
            f"INVOICE #: {invoice.number}",
            f"DATE: {invoice.date.strftime('%Y-%m-%d') if invoice.date else 'N/A'}",
            f"STATUS: {'PAID' if invoice.paid else 'UNPAID'}",
            "",
            f"CUSTOMER: {customer_name}",
            f"TICKET: #{invoice.ticket_id}" if invoice.ticket_id else "No linked ticket",
            "",
            f"TOTAL: ${invoice.total:.2f}",
            f"BALANCE DUE: ${invoice.balance_due:.2f}",
            "",
            "LINE ITEMS:",
            "-" * 30,
            self._format_line_items(invoice.line_items),
        ]

        content = "\n".join(content_parts)

        metadata: dict[str, Any] = {
            "invoice_number": invoice.number,
            "invoice_id": invoice.id,
            "customer_id": invoice.customer_id,
            "customer_name": customer_name,
            "ticket_id": invoice.ticket_id,
            "total": invoice.total,
            "paid": invoice.paid,
            "date": invoice.date.isoformat() if invoice.date else None,
        }

        return OnyxDocument(
            id=f"{DOC_PREFIX_INVOICE}{invoice.id}",
            sections=[DocumentSection(self._invoice_url(invoice.id), content)],
            source=DOCUMENT_SOURCE,
            semantic_identifier=semantic_id,
            metadata=metadata,
            doc_updated_at=invoice.updated_at,
            title=semantic_id,
        )
