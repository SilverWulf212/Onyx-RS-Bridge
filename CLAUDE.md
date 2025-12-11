# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Onyx-RS-Bridge is a Python connector that bridges RepairShopr (repair shop management system) with Onyx (AI-powered knowledge platform). It ingests tickets, customers, assets, and invoices from RepairShopr, enabling semantic search and AI-powered insights for repair technicians.

## Common Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run single test
pytest tests/test_models.py::test_name -v

# Linting
ruff check src/ tests/

# Type checking
mypy src/

# Format code
ruff format src/ tests/

# Test connection (requires RS_SUBDOMAIN and RS_API_KEY env vars)
python -m repairshopr_connector.connector

# CLI tool (after install)
rs-onyx
```

## Architecture

### Core Components

The connector implements three Onyx interfaces:
- **LoadConnector**: Full bulk sync of all data
- **PollConnector**: Incremental updates via `updated_at` timestamps
- **SlimConnector**: Lightweight ID-only fetch for pruning deleted records

### Key Modules

- `connector.py` - Main `RepairShoprConnector` class orchestrating sync operations with checkpoint/resume support
- `client.py` - `RepairShoprClient` handles all RS API communication with token bucket rate limiting (150 req/min), retry with exponential backoff, and connection pooling via httpx
- `models.py` - Pydantic models for RS API entities (RSTicket, RSCustomer, RSAsset, RSInvoice, RSComment)
- `document_builder.py` - Converts RS models to `OnyxDocument` format with rich searchable content
- `cache.py` - LRU cache with TTL for batch enrichment (eliminates N+1 queries)
- `state.py` - `StateManager` and `SyncCheckpoint` for crash recovery
- `rate_limiter.py` - Token bucket implementation for RS API rate limits

### Data Flow

1. Connector preloads all customers/assets into bounded cache
2. Iterates through tickets with pagination and deduplication
3. Enriches tickets from cache (no additional API calls)
4. DocumentBuilder converts to OnyxDocument with metadata for filtering
5. Yields batches of documents with checkpoint saves

### Document Types

Each RS entity becomes a prefixed Onyx document:
- `rs_ticket_{id}` - Primary documents with full context (comments, parts, customer/asset info)
- `rs_customer_{id}` - Customer profiles
- `rs_asset_{id}` - Device/equipment records
- `rs_invoice_{id}` - Invoice records (optional, disabled by default)

## Configuration

Required environment variables:
- `RS_SUBDOMAIN` - Your RepairShopr subdomain
- `RS_API_KEY` - API key from RS Admin -> Profile -> API Tokens

Key connector options:
- `include_internal_comments=False` - Security: hidden comments excluded by default
- `batch_size=50` - Documents per batch
- `cache_ttl_seconds=600` - Enrichment cache TTL

## API Rate Limits

RepairShopr allows 180 requests/minute. The client defaults to 150 for safety margin with automatic retry on 429 errors using exponential backoff.
