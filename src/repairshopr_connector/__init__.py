"""
Onyx RepairShopr Connector

A custom Onyx connector for ingesting tickets, customers, assets, and
other data from RepairShopr repair shop management system.
"""

from repairshopr_connector.connector import RepairShoprConnector
from repairshopr_connector.client import RepairShoprClient
from repairshopr_connector.models import (
    RSTicket,
    RSCustomer,
    RSAsset,
    RSComment,
    RSInvoice,
)

__version__ = "0.1.0"
__all__ = [
    "RepairShoprConnector",
    "RepairShoprClient",
    "RSTicket",
    "RSCustomer",
    "RSAsset",
    "RSComment",
    "RSInvoice",
]
