# Onyx-RepairShopr Bridge: Technical Architecture

## Executive Summary

This document outlines a bulletproof strategy for integrating RepairShopr (RS) ticket and customer data into Onyx, enabling AI-powered contextual search, recurring issue detection, and technician knowledge assistance.

## Why This Architecture Works

### The Problem
1. **Scattered Context**: Technicians lack visibility into historical patterns across tickets
2. **Missed Root Causes**: Recurring issues go undetected because data isn't correlated
3. **Knowledge Silos**: Valuable repair information is trapped in individual tickets
4. **No AI-Powered Search**: Can't ask natural language questions about repair history

### The Solution: Onyx Custom Connector

Onyx is an open-source AI platform specifically designed to:
- Ingest documents from 40+ sources via connectors
- Provide semantic search across all ingested data
- Use RAG (Retrieval Augmented Generation) to answer questions with context
- Maintain document-level permissions and access controls

By building a **custom RepairShopr connector**, we get:

| Capability | Benefit |
|------------|---------|
| **Full-text semantic search** | "Find all tickets about intermittent WiFi issues on Dell laptops" |
| **Cross-entity correlation** | Link tickets → customers → assets → comments |
| **Temporal analysis** | Detect patterns: "This customer has had 3 similar issues in 6 months" |
| **AI-powered Q&A** | Ask Onyx: "What was the root cause for ticket #4523?" |
| **Real-time sync** | Poll connector keeps data fresh automatically |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ONYX-RS-BRIDGE SYSTEM                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐         ┌──────────────────┐        ┌───────────────┐ │
│  │ RepairShopr │◄───────►│  RS Connector    │───────►│     ONYX      │ │
│  │    API      │  REST   │  (Python)        │  Docs  │   Platform    │ │
│  │             │  JSON   │                  │        │               │ │
│  └─────────────┘         │  - LoadConnector │        │  - Vespa DB   │ │
│                          │  - PollConnector │        │  - Embeddings │ │
│                          │  - SlimConnector │        │  - LLM Chat   │ │
│                          └──────────────────┘        └───────────────┘ │
│                                   │                          │         │
│                                   ▼                          ▼         │
│                          ┌──────────────────┐        ┌───────────────┐ │
│                          │ Document Builder │        │  Technician   │ │
│                          │                  │        │   Interface   │ │
│                          │ - Tickets        │        │               │ │
│                          │ - Customers      │        │  - Web UI     │ │
│                          │ - Assets         │        │  - Slack Bot  │ │
│                          │ - Comments       │        │  - API        │ │
│                          │ - Invoices       │        │               │ │
│                          └──────────────────┘        └───────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Component | Technology | Justification |
|-----------|------------|---------------|
| **Connector Runtime** | Python 3.11+ | Onyx connector standard |
| **HTTP Client** | `httpx` (async) | Modern, async-capable, connection pooling |
| **Rate Limiting** | `asyncio-throttle` | Respect RS's 180 req/min limit |
| **Data Validation** | `pydantic` | Type-safe RS API response parsing |
| **Caching** | Redis (optional) | Deduplicate during incremental syncs |
| **Configuration** | Environment variables + YAML | 12-factor app compliance |
| **Testing** | `pytest` + `pytest-asyncio` | Onyx testing standard |
| **Containerization** | Docker | Consistent deployment |

---

## RepairShopr API Integration

### Authentication
```
API Key: Obtained from RS Admin → Profile → API Tokens
Base URL: https://{subdomain}.repairshopr.com/api/v1
Rate Limit: 180 requests/minute
```

### Key Endpoints to Ingest

| Endpoint | Purpose | Sync Strategy |
|----------|---------|---------------|
| `GET /tickets.json` | All ticket data | Poll by `updated_at` |
| `GET /tickets/:id/comments` | Ticket comments/history | Linked to ticket |
| `GET /customers.json` | Customer profiles | Poll by `updated_at` |
| `GET /customer_assets.json` | Equipment/devices | Poll by `updated_at` |
| `GET /invoices.json` | Service history | Poll by `updated_at` |
| `GET /appointments.json` | Scheduled work | Poll by `updated_at` |

### Rate Limit Strategy
```python
# Adaptive rate limiting with exponential backoff
MAX_REQUESTS_PER_MINUTE = 180
SAFE_REQUESTS_PER_MINUTE = 150  # 83% utilization, leaves headroom
REQUEST_INTERVAL = 60 / SAFE_REQUESTS_PER_MINUTE  # ~0.4 seconds
```

---

## Onyx Document Model

### Document Structure for Tickets

Each RS ticket becomes an Onyx document with rich metadata:

```python
Document(
    id="rs_ticket_{ticket_id}",

    # Searchable content sections
    sections=[
        Section(
            link=f"https://{subdomain}.repairshopr.com/tickets/{ticket_id}",
            text=f"""
            TICKET #{number}: {subject}

            STATUS: {status}
            PROBLEM TYPE: {problem_type}
            PRIORITY: {priority}

            CUSTOMER: {customer.business_name or customer.full_name}
            ASSET: {asset.name} (Serial: {asset.serial})

            DESCRIPTION:
            {problem_description}

            RESOLUTION:
            {resolution_notes}

            COMMENTS/HISTORY:
            {formatted_comments}

            PARTS USED:
            {line_items}
            """
        )
    ],

    # Source identifier
    source=DocumentSource.REPAIRSHOPR,  # Custom enum value

    # Human-readable title for search results
    semantic_identifier=f"Ticket #{number}: {subject}",

    # Structured metadata for filtering
    metadata={
        "ticket_number": number,
        "status": status,
        "problem_type": problem_type,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "asset_id": asset_id,
        "asset_type": asset_type,
        "asset_serial": asset_serial,
        "created_at": created_at,
        "resolved_at": resolved_at,
        "technician": assigned_tech,
        "location": location_name,
        "total_cost": total_cost,
        "labor_hours": labor_hours,
    },

    # Timestamps for incremental sync
    doc_updated_at=updated_at,

    # Ownership for attribution
    primary_owners=[BasicExpertInfo(display_name=assigned_tech)],
    secondary_owners=[BasicExpertInfo(display_name=customer_name)],
)
```

### Document Types to Create

| RS Entity | Onyx Document Type | Relationship |
|-----------|-------------------|--------------|
| Ticket | `rs_ticket_{id}` | Primary document |
| Customer | `rs_customer_{id}` | Referenced by tickets |
| Asset | `rs_asset_{id}` | Referenced by tickets |
| Invoice | `rs_invoice_{id}` | Linked to tickets |

---

## Connector Implementation

### File Structure

```
onyx-rs-bridge/
├── src/
│   └── repairshopr_connector/
│       ├── __init__.py
│       ├── connector.py          # Main connector class
│       ├── client.py             # RS API client
│       ├── models.py             # Pydantic models for RS API
│       ├── document_builder.py   # Convert RS → Onyx documents
│       ├── rate_limiter.py       # Rate limiting logic
│       └── utils.py              # Helpers
├── tests/
│   ├── conftest.py
│   ├── test_connector.py
│   ├── test_client.py
│   └── fixtures/                 # Mock RS API responses
├── config/
│   └── connector_config.yaml
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── pyproject.toml
├── README.md
└── ARCHITECTURE.md
```

### Connector Class Design

```python
from onyx.connectors.interfaces import LoadConnector, PollConnector, SlimConnector
from onyx.connectors.models import Document, ConnectorMissingCredentialError

class RepairShoprConnector(LoadConnector, PollConnector, SlimConnector):
    """
    Onyx connector for RepairShopr repair shop management system.

    Supports:
    - Full load: Initial bulk ingestion of all tickets/customers/assets
    - Poll: Incremental updates based on updated_at timestamps
    - Slim: Lightweight existence checks for pruning deleted records
    """

    def __init__(
        self,
        subdomain: str,
        include_tickets: bool = True,
        include_customers: bool = True,
        include_assets: bool = True,
        include_invoices: bool = False,
        ticket_statuses: list[str] | None = None,  # Filter by status
        problem_types: list[str] | None = None,    # Filter by type
    ):
        self.subdomain = subdomain
        self.include_tickets = include_tickets
        self.include_customers = include_customers
        self.include_assets = include_assets
        self.include_invoices = include_invoices
        self.ticket_statuses = ticket_statuses
        self.problem_types = problem_types
        self.client: RepairShoprClient | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        """Load API key from Onyx credential store."""
        api_key = credentials.get("api_key")
        if not api_key:
            raise ConnectorMissingCredentialError("RepairShopr API key required")

        self.client = RepairShoprClient(
            subdomain=self.subdomain,
            api_key=api_key,
        )

    def load_from_state(self) -> GenerateDocumentsOutput:
        """Full load - fetch all documents."""
        yield from self._fetch_all_documents()

    def poll_source(
        self,
        start: SecondsSinceUnixEpoch,
        end: SecondsSinceUnixEpoch
    ) -> GenerateDocumentsOutput:
        """Incremental load - fetch documents updated since last poll."""
        yield from self._fetch_documents_in_range(start, end)

    def retrieve_all_slim_documents(self) -> GenerateSlimDocumentOutput:
        """Return only document IDs for pruning check."""
        yield from self._fetch_document_ids_only()
```

---

## Recurring Issue Detection Strategy

### Why This Works

Onyx's semantic search + metadata filtering enables powerful pattern detection:

```
┌─────────────────────────────────────────────────────────────────┐
│                    PATTERN DETECTION FLOW                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. TECHNICIAN CREATES NEW TICKET                               │
│     "Customer reports laptop overheating"                       │
│                                    │                            │
│                                    ▼                            │
│  2. ONYX AUTOMATICALLY SEARCHES                                 │
│     Query: Similar tickets for this:                            │
│     - Customer (customer_id filter)                             │
│     - Asset (asset_serial filter)                               │
│     - Problem type (semantic similarity)                        │
│                                    │                            │
│                                    ▼                            │
│  3. SURFACE RELATED TICKETS                                     │
│     "Found 3 related tickets in past 12 months:                 │
│      - Ticket #1234: Thermal paste replacement (6 mo ago)       │
│      - Ticket #892: Fan cleaning (9 mo ago)                     │
│      - Ticket #445: Overheating complaint (12 mo ago)"          │
│                                    │                            │
│                                    ▼                            │
│  4. AI INSIGHT                                                  │
│     "Pattern detected: This laptop has recurring thermal        │
│      issues. Previous fixes were temporary. Consider            │
│      recommending motherboard replacement or new device."       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation Approaches

#### Approach 1: Onyx Native Search (Recommended)

Use Onyx's built-in semantic search with metadata filters:

```python
# Pseudo-code for technician interface
def find_related_issues(ticket):
    results = onyx.search(
        query=ticket.problem_description,
        filters={
            "source": "REPAIRSHOPR",
            "customer_id": ticket.customer_id,
        },
        num_results=10,
    )
    return results

def find_asset_history(asset_serial):
    results = onyx.search(
        query="*",  # All documents
        filters={
            "source": "REPAIRSHOPR",
            "asset_serial": asset_serial,
        },
        sort_by="created_at",
        num_results=50,
    )
    return results
```

#### Approach 2: Onyx AI Agent

Configure an Onyx Agent with RepairShopr context:

```yaml
# Onyx Agent Configuration
name: "RepairShopr Assistant"
description: "AI assistant for technicians with access to repair history"
system_prompt: |
  You are a repair shop assistant with access to RepairShopr ticket history.

  When a technician describes an issue:
  1. Search for similar past tickets
  2. Look for patterns in the customer's history
  3. Check the asset's repair history
  4. Identify potential root causes based on recurring issues
  5. Suggest solutions that worked before

  Always cite specific ticket numbers and dates.
```

#### Approach 3: Custom Analytics Layer

For advanced pattern detection, add a lightweight analytics service:

```python
class RecurringIssueDetector:
    """Detect patterns across RepairShopr tickets in Onyx."""

    def analyze_customer_patterns(self, customer_id: str) -> PatternReport:
        """Find recurring issues for a specific customer."""
        tickets = self.onyx.search(
            filters={"customer_id": customer_id},
            num_results=100,
        )

        # Group by problem_type
        problem_frequency = Counter(t.metadata["problem_type"] for t in tickets)

        # Find repeat issues (same problem_type within 90 days)
        repeat_issues = self._find_repeats(tickets, window_days=90)

        return PatternReport(
            customer_id=customer_id,
            total_tickets=len(tickets),
            problem_frequency=problem_frequency,
            repeat_issues=repeat_issues,
            recommended_actions=self._generate_recommendations(repeat_issues),
        )

    def analyze_asset_patterns(self, asset_serial: str) -> PatternReport:
        """Find recurring issues for a specific device/asset."""
        # Similar analysis by asset
        pass

    def find_systemic_issues(self, problem_type: str) -> SystemicReport:
        """Find patterns across all customers for a problem type."""
        # Identify if an issue is widespread (e.g., bad batch of parts)
        pass
```

---

## Data Flow & Sync Strategy

### Initial Load (Day 1)

```
1. Full historical load of all entities
2. Estimated time: ~2-4 hours for 10,000 tickets
3. Rate limited to 150 req/min

Timeline:
─────────────────────────────────────────────────────────
│ Customers │ Assets │    Tickets + Comments   │ Index │
│  ~30 min  │ ~30 min│       ~2-3 hours        │ ~30m  │
─────────────────────────────────────────────────────────
```

### Ongoing Sync (Daily)

```
Poll Interval: Every 10 minutes (configurable)
Strategy: Fetch records where updated_at > last_poll_time

Benefits:
- Minimal API calls (only changed records)
- Near real-time updates
- Handles edits to existing tickets
```

### Pruning (Weekly)

```
Slim Connector runs weekly to:
- Fetch all document IDs from RepairShopr
- Compare against Onyx index
- Remove documents deleted from RS
```

---

## Configuration

### Environment Variables

```bash
# RepairShopr Configuration
RS_SUBDOMAIN=yourcompany
RS_API_KEY=your-api-key-here

# Sync Configuration
RS_POLL_INTERVAL_MINUTES=10
RS_FULL_SYNC_ENABLED=true
RS_INCLUDE_TICKETS=true
RS_INCLUDE_CUSTOMERS=true
RS_INCLUDE_ASSETS=true
RS_INCLUDE_INVOICES=false

# Filtering (optional)
RS_TICKET_STATUSES=New,In Progress,Resolved  # Empty = all
RS_PROBLEM_TYPES=                             # Empty = all
RS_LOCATIONS=                                 # Empty = all

# Rate Limiting
RS_REQUESTS_PER_MINUTE=150

# Onyx Configuration
ONYX_API_URL=http://localhost:8080
ONYX_API_KEY=your-onyx-api-key
```

### Onyx Admin Setup

```yaml
# Add to Onyx's connector configuration
connector:
  name: RepairShopr
  source: REPAIRSHOPR
  connector_class: repairshopr_connector.RepairShoprConnector
  credential_type: api_key
  config_schema:
    subdomain:
      type: string
      required: true
      description: "Your RepairShopr subdomain (e.g., 'yourcompany')"
    include_tickets:
      type: boolean
      default: true
    include_customers:
      type: boolean
      default: true
    include_assets:
      type: boolean
      default: true
```

---

## Security Considerations

| Concern | Mitigation |
|---------|------------|
| API Key Storage | Use Onyx's encrypted credential store |
| Data in Transit | HTTPS enforced for RS API calls |
| Access Control | Onyx user permissions limit who can search |
| PII Handling | Customer data searchable only by authorized users |
| Audit Logging | All searches logged by Onyx |

---

## Deployment Options

### Option 1: Native Onyx Connector (Recommended)

Deploy as part of Onyx installation:

```bash
# Add connector to Onyx's backend
cp -r repairshopr_connector/ onyx/backend/onyx/connectors/

# Register in DocumentSource enum
# Add to SOURCE_METADATA_MAP
# Rebuild Onyx
```

### Option 2: Standalone Service with Ingestion API

Run bridge separately, push to Onyx via API:

```bash
# Docker deployment
docker-compose up -d repairshopr-bridge

# Bridge fetches from RS, pushes to Onyx Ingestion API
```

### Option 3: Hybrid (Development → Production)

1. Start with Ingestion API for rapid development
2. Graduate to native connector for production stability

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Sync Latency | < 15 min | Time from RS update to Onyx availability |
| Search Relevance | > 90% | Technician satisfaction surveys |
| Pattern Detection Rate | > 80% | Recurring issues flagged before escalation |
| API Error Rate | < 0.1% | Monitoring dashboard |
| Index Completeness | 100% | All RS tickets in Onyx |

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Set up project structure
- [ ] Implement RS API client with rate limiting
- [ ] Create Pydantic models for RS entities
- [ ] Basic ticket document builder

### Phase 2: Core Connector (Week 2-3)
- [ ] Implement LoadConnector (full sync)
- [ ] Implement PollConnector (incremental sync)
- [ ] Add customer and asset document types
- [ ] Comprehensive test suite

### Phase 3: Integration (Week 3-4)
- [ ] Integrate with Onyx (native or API)
- [ ] Configure Onyx Agent for RS
- [ ] Build technician search interface
- [ ] Documentation and training

### Phase 4: Intelligence (Week 4+)
- [ ] Pattern detection algorithms
- [ ] Recurring issue alerts
- [ ] Dashboard for insights
- [ ] Feedback loop for improvements

---

## Appendix: RepairShopr API Reference

### Tickets
```
GET  /api/v1/tickets.json?api_key={key}&page={n}
GET  /api/v1/tickets/{id}?api_key={key}
POST /api/v1/tickets/{id}/comment?api_key={key}
```

### Customers
```
GET  /api/v1/customers.json?api_key={key}&query={search}
GET  /api/v1/customers/{id}?api_key={key}
```

### Assets
```
GET  /api/v1/customer_assets.json?api_key={key}&customer_id={id}
GET  /api/v1/customer_assets/{id}?api_key={key}
```

### Rate Limits
- 180 requests per minute per IP
- Recommended: Stay under 150 for safety margin

---

## Sources

- [RepairShopr API Documentation](https://api-docs.repairshopr.com/)
- [RepairShopr REST API Help](https://repair.uservoice.com/knowledgebase/articles/376312-repairshopr-http-rest-api-beta)
- [Onyx GitHub Repository](https://github.com/onyx-dot-app/onyx)
- [Onyx Connector Guide](https://docs.onyx.app/developers/guides/create_connector)
- [Onyx Connector README](https://github.com/onyx-dot-app/onyx/blob/main/backend/onyx/connectors/README.md)
- [Onyx Connector Models](https://github.com/onyx-dot-app/onyx/blob/main/backend/onyx/connectors/models.py)
