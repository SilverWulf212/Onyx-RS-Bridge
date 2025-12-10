# Onyx-RS-Bridge

**AI-Powered Knowledge Base for RepairShopr Repair Shops**

A custom Onyx connector that ingests tickets, customers, assets, and invoices from RepairShopr, enabling AI-powered semantic search and recurring issue detection for repair technicians.

## Why This Exists

Repair shops using RepairShopr have valuable historical data trapped in individual tickets. This connector bridges that gap by:

- **Semantic Search**: Ask natural language questions like "What fixes have worked for Dell laptops with blue screen errors?"
- **Pattern Detection**: Automatically surface recurring issues for customers or devices
- **Context Awareness**: See full repair history when opening a new ticket
- **AI-Powered Insights**: Let Onyx identify root causes that humans might miss

## Features

| Feature | Description |
|---------|-------------|
| Full Data Sync | Tickets, customers, assets, invoices |
| Incremental Updates | Poll-based sync every 10 minutes |
| Rich Document Content | Comments, parts, labor, relationships |
| Metadata Filtering | Search by status, customer, asset, tech |
| Rate Limit Handling | Respects RS's 180 req/min limit |
| Pruning Support | Detects and removes deleted records |

## Quick Start

### Prerequisites

- Python 3.11+
- RepairShopr account with API access
- Onyx instance (self-hosted or cloud)

### Installation

```bash
# Clone the repository
git clone https://github.com/SilverWulf212/Onyx-RS-Bridge.git
cd Onyx-RS-Bridge

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# For development
pip install -e ".[dev]"
```

### Configuration

1. Copy the example environment file:

```bash
cp config/.env.example .env
```

2. Edit `.env` with your credentials:

```bash
RS_SUBDOMAIN=yourcompany      # From yourcompany.repairshopr.com
RS_API_KEY=your-api-key       # From RS Admin -> Profile -> API Tokens
```

3. Get your RepairShopr API key:
   - Log into RepairShopr
   - Click your name (top right) → Profile/Password
   - Click "API Tokens"
   - Generate a new token

### Test the Connection

```bash
# Set environment variables
export RS_SUBDOMAIN=yourcompany
export RS_API_KEY=your-api-key

# Run a test fetch
python -m repairshopr_connector.connector
```

## Integration with Onyx

### Option 1: Native Connector (Recommended)

Add the connector to your Onyx installation:

```bash
# Copy connector to Onyx
cp -r src/repairshopr_connector /path/to/onyx/backend/onyx/connectors/

# Add to DocumentSource enum in constants.py
# Add to SOURCE_METADATA_MAP in sources.ts
# Rebuild Onyx
```

### Option 2: Ingestion API

Push documents to Onyx via the Ingestion API:

```python
from repairshopr_connector import RepairShoprConnector
import httpx

connector = RepairShoprConnector(subdomain="yourcompany")
connector.load_credentials({"api_key": "your-api-key"})

async with httpx.AsyncClient() as client:
    for batch in connector.load_from_state():
        response = await client.post(
            "http://onyx:8080/api/ingestion/documents",
            json=[doc.to_dict() for doc in batch],
            headers={"Authorization": "Bearer your-onyx-key"}
        )
```

### Option 3: Docker

```bash
cd docker
cp ../config/.env.example .env
# Edit .env with your credentials

docker-compose up -d
```

## Architecture

```
RepairShopr API  →  RS Connector  →  Onyx Platform  →  Technician UI
     │                   │                │                  │
     │   Tickets         │   Documents    │   Embeddings     │   Semantic
     │   Customers       │   Metadata     │   Vector DB      │   Search
     │   Assets          │   Enrichment   │   LLM Chat       │   Insights
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed technical documentation.

## Document Types

### Tickets

Each ticket becomes a searchable document including:
- Subject, status, problem type, priority
- Full problem description and resolution notes
- Complete comment/update history
- Parts and labor line items
- Customer and asset context

### Customers

Customer profiles for context:
- Business/individual name
- Contact information
- Address
- Notes and preferences

### Assets

Device/equipment records:
- Name, type, serial number
- Manufacturer, model, OS
- Owner information

## Use Cases

### 1. Find Similar Past Issues

> "Show me tickets for laptops that won't boot"

Onyx searches across all ticket content and returns semantically similar issues, even if they use different terminology.

### 2. Customer History Lookup

> "What issues has Acme Corporation had in the past year?"

Filter by customer to see their complete repair history.

### 3. Device Pattern Analysis

> "Find all tickets for serial number ABC123XYZ"

See the complete repair history for a specific device to identify recurring problems.

### 4. Root Cause Investigation

> "What were the root causes for overheating issues on Dell laptops?"

Let Onyx's AI analyze patterns across multiple tickets to identify common causes.

## Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| `RS_SUBDOMAIN` | Your RepairShopr subdomain | Required |
| `RS_API_KEY` | API key from RS profile | Required |
| `RS_INCLUDE_TICKETS` | Sync tickets | `true` |
| `RS_INCLUDE_CUSTOMERS` | Sync customers | `true` |
| `RS_INCLUDE_ASSETS` | Sync assets | `true` |
| `RS_INCLUDE_INVOICES` | Sync invoices | `false` |
| `RS_POLL_INTERVAL_MINUTES` | Incremental sync interval | `10` |
| `RS_REQUESTS_PER_MINUTE` | API rate limit | `150` |

## Development

### Run Tests

```bash
pytest tests/ -v
```

### Code Quality

```bash
# Linting
ruff check src/ tests/

# Type checking
mypy src/

# Format
ruff format src/ tests/
```

### Project Structure

```
onyx-rs-bridge/
├── src/repairshopr_connector/
│   ├── __init__.py           # Package exports
│   ├── connector.py          # Main connector class
│   ├── client.py             # RS API client
│   ├── models.py             # Pydantic models
│   └── document_builder.py   # RS → Onyx conversion
├── tests/
│   ├── conftest.py           # Test fixtures
│   ├── test_models.py        # Model tests
│   └── test_document_builder.py
├── config/
│   ├── connector_config.yaml # Onyx connector config
│   └── .env.example          # Environment template
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── ARCHITECTURE.md           # Technical documentation
├── pyproject.toml            # Python project config
└── README.md
```

## API Reference

### RepairShopr Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /tickets.json` | List tickets with pagination |
| `GET /tickets/:id/comments` | Get ticket comments |
| `GET /customers.json` | List customers |
| `GET /customer_assets.json` | List assets |
| `GET /invoices.json` | List invoices |

### Rate Limits

- RepairShopr allows 180 requests/minute per IP
- Connector uses 150 req/min for safety margin
- Automatic retry with exponential backoff on rate limit errors

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - See LICENSE file for details.

## Support

- [RepairShopr API Docs](https://api-docs.repairshopr.com/)
- [Onyx Documentation](https://docs.onyx.app/)
- [Create an Issue](https://github.com/SilverWulf212/Onyx-RS-Bridge/issues)
