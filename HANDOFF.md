# Developer Handoff: Onyx-RS-Bridge

**Last Updated:** 2025-12-11 03:35 UTC

## Project Overview

This is a connector that bridges RepairShopr (repair shop management system) with Onyx (self-hosted AI knowledge platform). It fetches tickets, customers, and assets from RepairShopr and ingests them into Onyx for semantic search and AI-powered insights.

## Current Status

**Working:**
- RepairShopr API client with rate limiting (150 req/min)
- Fetching tickets, customers, assets from RS
- Building Onyx-compatible documents
- Checkpoint/resume for crash recovery
- Docker deployment on same host as Onyx
- Connected to `onyx_default` Docker network
- Container stays alive after sync for debugging

**In Progress / Current Issue:**
- Onyx ingestion API returning errors (all 50 docs failed)
- Added debug logging to see actual Onyx error response
- Need to find correct Onyx API endpoint for document ingestion

**Not Yet Implemented:**
- Incremental polling (only full sync works)
- Proper Onyx connector registration (using direct API calls instead)

## Environment

- **Server:** Alphawulf (Ubuntu)
- **Deployment:** Docker on same host as Onyx
- **Onyx Network:** `onyx_default`
- **Onyx API Server:** `onyx-api_server-1:8080` (internal Docker network)

## Credentials (stored in `/root/Onyx-RS-Bridge/docker/.env`)

```
RS_SUBDOMAIN=silverwulf
RS_API_KEY=T5056bba2f5efa4618-e0c310911aa2671cb9195813f2273f5e
ONYX_API_URL=http://onyx-api_server-1:8080
ONYX_API_KEY=on_9ClEKfKrb1Cr8l9d6Tx7bqS8Cb1W9fWJItdkzpuDPR7VhW03LFt3rQnNmTo1h1fbhPhh9MfMaM0EmzVfhpYYonjD8Cs9MIko2E3N7X30JqqjbZ2Se4m_20EP4p5wNo1aa5HrhxvJW1zmXhXoRxppRe1zDDV1cjCs5rLQa0U0WqQx_OiPJSIjCW4IzGzW8t39Nfb40R8BV_fyCJnQ5p2WtxG11zGyzDwgiOb3DMhD_DayYboOqCIVdxBGMCJKXm9n
```

## Scale

- **22,056 tickets** in RepairShopr (not a typo)
- Full sync will make ~23,000+ API calls to RepairShopr
- Rate limited at 150 req/min = ~2.5 hours for full sync

## Key Files

| File | Purpose |
|------|---------|
| `src/repairshopr_connector/connector.py` | Main connector class, orchestrates sync |
| `src/repairshopr_connector/client.py` | RepairShopr API client with rate limiting |
| `src/repairshopr_connector/cli.py` | CLI commands (`rs-onyx sync/test/status`) |
| `src/repairshopr_connector/document_builder.py` | Converts RS data to Onyx documents |
| `src/repairshopr_connector/models.py` | Pydantic models for RS API responses |
| `docker/docker-compose.yml` | Docker deployment config |
| `docker/.env` | Production credentials (on server) |

## Commands on Server

```bash
# Navigate to project
cd ~/Onyx-RS-Bridge/docker

# View logs
docker logs -f rs-onyx-connector

# Restart with rebuild
docker compose down && docker compose up -d --build

# Full rebuild (clears state)
docker compose down -v && docker compose up -d --build

# Pull latest code and rebuild
cd ~/Onyx-RS-Bridge && git pull && cd docker && docker compose up -d --build
```

## Issues Encountered & Fixed

1. **Dockerfile missing README.md** - Build failed because `pyproject.toml` references README.md
   - Fix: Added `COPY README.md` to Dockerfile
   - Commit: `cf864f9`

2. **No `__main__` entry point** - Container kept restarting
   - Fix: Changed CMD to `rs-onyx sync`
   - Commit: `fae2c67`

3. **Permission denied on state file** - Docker volume owned by root, container runs as `connector` user
   - Fix: Added `mkdir` and `chown` for state directory in Dockerfile
   - Commit: `cf1103d`

4. **structlog.stdlib.INFO error** - Wrong import for tenacity retry logging
   - Fix: Changed to string `"INFO"` instead of `structlog.stdlib.INFO`
   - Commit: `e64f845`

5. **Docker network not connected to Onyx** - Couldn't reach Onyx API
   - Fix: Connected to `onyx_default` external network
   - Commit: `ee6cb14`

6. **Container exits after sync** - Can't exec into container to debug
   - Fix: Changed CMD to run sync then `sleep infinity`
   - Commit: `4ab9914`

7. **Onyx API errors not visible** - All 50 docs failed but no error details
   - Fix: Added debug logging to print endpoint and first 3 error responses
   - Commit: `4ab9914`

8. **Wrong Onyx API endpoint** - Was using `/api/v1/manage/admin/connector/file/upload` (404)
   - Discovery: Used `find_endpoints.py` to query `/openapi.json`
   - Found correct endpoint: `/onyx-api/ingestion` ("Upsert Ingestion Doc")
   - Fix: Updated `cli.py` to use correct endpoint
   - Commit: `1f25188`

9. **Schema mismatch with Onyx** - Documents rejected due to format issues
   - Problem 1: `source` field set to "REPAIRSHOPR" (not valid enum) → Set to `null`
   - Problem 2: `metadata` had int/bool/null values → Convert all to strings
   - Problem 3: Missing `from_ingestion_api: true` flag → Added
   - Fix: Updated `document_builder.py` with `_stringify_metadata()` helper
   - Commit: (pending)

## Current Status & Path to MVP

### Where We Are Now

1. **RepairShopr side: WORKING** ✅
   - Fetching tickets, customers, assets from RS API
   - Rate limiting, retry logic, checkpoint/resume all working
   - Documents being built correctly

2. **Onyx side: SCHEMA MISMATCH** ❌
   - Found correct endpoint: `POST /onyx-api/ingestion`
   - Our document format has **3 critical mismatches** with Onyx's expected schema

### Schema Analysis (Deep Dive)

**What Onyx Expects (from OpenAPI spec):**

```
DocumentBase (required fields):
  - sections: array of TextSection {link: str, text: str}
  - semantic_identifier: string
  - metadata: object with STRING values only (no int/bool/null)

Optional fields:
  - id: string | null
  - source: DocumentSource enum | null
  - doc_updated_at: datetime string | null
  - primary_owners: array of BasicExpertInfo | null
  - secondary_owners: array of BasicExpertInfo | null
  - title: string | null
  - from_ingestion_api: boolean (default false)
```

**What We're Sending:**

```python
# From document_builder.py OnyxDocument.to_dict()
{
  "id": "rs_ticket_12345",           # ✅ OK
  "sections": [{"link": "...", "text": "..."}],  # ✅ OK
  "source": "REPAIRSHOPR",           # ❌ PROBLEM: Not a valid DocumentSource enum
  "semantic_identifier": "...",       # ✅ OK
  "metadata": {
    "ticket_number": 1001,           # ❌ PROBLEM: integer, not string
    "is_resolved": false,            # ❌ PROBLEM: boolean, not string
    "customer_id": 5001,             # ❌ PROBLEM: integer, not string
    ...
  },
  "doc_updated_at": "2024-01-15T...", # ✅ OK
  "primary_owners": [...],            # ✅ OK
  "secondary_owners": [...],          # ✅ OK
  "title": "..."                      # ✅ OK
}
```

### The 3 Problems to Fix

#### Problem 1: `source` Field
Onyx expects a `DocumentSource` enum value. "REPAIRSHOPR" is not in that enum.

**Options:**
- A) Set `source: null` and let Onyx use default (SAFEST - try this first)
- B) Use an existing enum value like "NOT_APPLICABLE" or "INGESTION_API"
- C) Check if Onyx allows custom sources via config

#### Problem 2: `metadata` Values Must Be Strings
Our metadata contains integers, booleans, and nulls. Onyx requires all values to be strings or arrays of strings.

**Fix:** Convert all metadata values to strings:
```python
def _stringify_metadata(metadata: dict) -> dict:
    result = {}
    for key, value in metadata.items():
        if value is None:
            continue  # Skip nulls
        elif isinstance(value, bool):
            result[key] = "true" if value else "false"
        elif isinstance(value, (int, float)):
            result[key] = str(value)
        else:
            result[key] = value
    return result
```

#### Problem 3: Test with Real Endpoint
We changed the endpoint to `/onyx-api/ingestion` but haven't tested yet.

### Recommended Path to MVP

**Step 1: Quick Fix (5 min)**
Modify `document_builder.py` to:
1. Set `source = None` instead of "REPAIRSHOPR"
2. Add `_stringify_metadata()` helper
3. Add `from_ingestion_api = True` to output

**Step 2: Rebuild & Test (10 min)**
```bash
cd ~/Onyx-RS-Bridge && git pull
cd docker && docker compose down -v && docker compose up -d --build
docker logs -f rs-onyx-connector
```

**Step 3: Verify Success**
- Should see "Sent to Onyx: 50" instead of "Failed: 50"
- Check Onyx UI for documents

**Step 4: Debug if Still Failing**
- Check error response for specific field issues
- Run `check_section_schema.py` to verify TextSection format

### Debug Scripts Available

| Script | Purpose |
|--------|---------|
| `docker/probe_onyx.py` | Check which endpoints exist |
| `docker/find_endpoints.py` | Find document/ingestion endpoints |
| `docker/check_ingestion_schema.py` | Show ingestion endpoint schema |
| `docker/check_document_base.py` | Show DocumentBase schema |
| `docker/check_section_schema.py` | Show TextSection/DocumentSource schemas |

Usage: `cat docker/<script>.py | docker exec -i rs-onyx-connector python3`

## Architecture

```
RepairShopr API
      │
      ▼
┌─────────────────┐
│  RS Connector   │ (Docker: rs-onyx-connector)
│  - Fetches data │
│  - Rate limits  │
│  - Builds docs  │
└────────┬────────┘
         │
         ▼ (onyx_default network)
┌─────────────────┐
│  Onyx API       │ (Docker: onyx-api_server-1:8080)
│  - Ingestion    │
│  - Embeddings   │
│  - Search       │
└─────────────────┘
```

## Next Steps

1. **Debug Onyx ingestion** - Check logs for HTTP errors, find correct API endpoint
2. **Test with small batch** - Modify to only sync 1-2 tickets first
3. **Verify documents in Onyx** - Check Onyx UI for ingested documents
4. **Scale up** - Once working, run full 22k ticket sync
5. **Add incremental sync** - Poll for changes instead of full sync each time

## Contact

- **Repo:** https://github.com/SilverWulf212/Onyx-RS-Bridge
- **RepairShopr Instance:** silverwulf.repairshopr.com
