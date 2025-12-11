# Developer Handoff: Onyx-RS-Bridge

**Last Updated:** 2025-12-11 03:25 UTC

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
   - Commit: (pending)

## Current Status & Path to MVP

### Where We Are Now

1. **RepairShopr side: WORKING** ✅
   - Fetching tickets, customers, assets from RS API
   - Rate limiting, retry logic, checkpoint/resume all working
   - Documents being built correctly

2. **Onyx side: ALMOST WORKING** 🔄
   - Found correct endpoint: `POST /onyx-api/ingestion`
   - Discovered via OpenAPI spec at `/openapi.json`
   - Need to verify our document format matches Onyx's `DocumentBase` schema

### What We Just Discovered

**Correct Onyx Ingestion Endpoint:**
```
POST /onyx-api/ingestion
Summary: "Upsert Ingestion Doc"
```

**Expected Payload Structure:**
```json
{
  "document": {
    // DocumentBase schema - need to verify fields match
  },
  "cc_pair_id": null  // optional
}
```

### Next Steps to MVP

1. **Check DocumentBase schema** (in progress)
   - Run: `cat docker/check_document_base.py | docker exec -i rs-onyx-connector python3`
   - Compare with our `OnyxDocument.to_dict()` output

2. **Fix payload format if needed**
   - Our `document_builder.py` creates documents with: id, sections, source, semantic_identifier, metadata, doc_updated_at, primary_owners, secondary_owners, title
   - Onyx may expect different field names or structure

3. **Rebuild and test with small batch**
   - Once schema matches, rebuild container
   - Run sync - should see "Sent to Onyx: 50" instead of "Failed: 50"

4. **Verify in Onyx UI**
   - Check Onyx web interface for ingested documents
   - Test search functionality

5. **Scale to full 22k tickets**
   - Once MVP works, run full sync
   - Monitor for rate limits or errors

### Debug Scripts Available

| Script | Purpose |
|--------|---------|
| `docker/probe_onyx.py` | Check which endpoints exist |
| `docker/find_endpoints.py` | Find document/ingestion endpoints |
| `docker/check_ingestion_schema.py` | Show ingestion endpoint schema |
| `docker/check_document_base.py` | Show DocumentBase schema |

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
