# Developer Handoff: Onyx-RS-Bridge

**Last Updated:** 2025-12-11 04:40 UTC

## Project Overview

This is a connector that bridges RepairShopr (repair shop management system) with Onyx (self-hosted AI knowledge platform). It fetches tickets, customers, and assets from RepairShopr and ingests them into Onyx for semantic search and AI-powered insights.

## Current Status: WORKING ✅

**All Major Components Operational:**
- ✅ RepairShopr API client with rate limiting (150 req/min)
- ✅ Fetching tickets, customers, assets from RS
- ✅ Building Onyx-compatible documents
- ✅ Checkpoint/resume for crash recovery
- ✅ Docker deployment on same host as Onyx
- ✅ Connected to `onyx_default` Docker network
- ✅ Onyx authentication (Bearer token)
- ✅ Document ingestion to Onyx
- ✅ Retry logic with exponential backoff
- ✅ Rate limit (429) and server error (5xx) handling

**Not Yet Implemented:**
- Incremental polling (only full sync works)
- Batch ingestion (sends one doc at a time)

## Environment

- **Server:** Alphawulf (Ubuntu, 10th gen i5, 32GB RAM, 1TB M.2, NO GPU)
- **Deployment:** Docker on same host as Onyx
- **Onyx Network:** `onyx_default`
- **Onyx API Server:** `onyx-api_server-1:8080` (internal Docker network)
- **Embedding:** CPU-based (slower, 120s timeout configured)

## Credentials (stored in `/root/Onyx-RS-Bridge/docker/.env`)

```
RS_SUBDOMAIN=silverwulf
RS_API_KEY=T5056bba2f5efa4618-e0c310911aa2671cb9195813f2273f5e
ONYX_API_URL=http://onyx-api_server-1:8080
ONYX_API_KEY=on_9ClEKfKrb1Cr8l9d6Tx7bqS8Cb1W9fWJItdkzpuDPR7VhW03LFt3rQnNmTo1h1fbhPhh9MfMaM0EmzVfhpYYonjD8Cs9MIko2E3N7X30JqqjbZ2Se4m_20EP4p5wNo1aa5HrhxvJW1zmXhXoRxppRe1zDDV1cjCs5rLQa0U0WqQx_OiPJSIjCW4IzGzW8t39Nfb40R8BV_fyCJnQ5p2WtxG11zGyzDwgiOb3DMhD_DayYboOqCIVdxBGMCJKXm9n
```

⚠️ **CRITICAL:** Ensure no extra whitespace/newlines in API key. This was the root cause of the initial auth failures.

## Scale

- **22,056 tickets** in RepairShopr
- Full sync will make ~23,000+ API calls to RepairShopr
- Rate limited at 150 req/min = ~2.5 hours for full sync
- CPU embeddings add additional time per document

## Key Files

| File | Purpose |
|------|---------|
| `src/repairshopr_connector/connector.py` | Main connector class, orchestrates sync |
| `src/repairshopr_connector/client.py` | RepairShopr API client with rate limiting |
| `src/repairshopr_connector/cli.py` | CLI commands (`rs-onyx sync/test/status`) + Onyx ingestion |
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

# Run sync with verbose output
docker exec rs-onyx-connector rs-onyx sync --verbose
```

## Issues Encountered & Fixed

1. **Dockerfile missing README.md** - Build failed
   - Fix: Added `COPY README.md` to Dockerfile

2. **No `__main__` entry point** - Container kept restarting
   - Fix: Changed CMD to `rs-onyx sync`

3. **Permission denied on state file** - Docker volume owned by root
   - Fix: Added `mkdir` and `chown` for state directory

4. **structlog.stdlib.INFO error** - Wrong import for tenacity
   - Fix: Changed to string `"INFO"`

5. **Docker network not connected to Onyx** - Couldn't reach API
   - Fix: Connected to `onyx_default` external network

6. **Container exits after sync** - Can't exec into container
   - Fix: Changed CMD to run sync then `sleep infinity`

7. **Wrong Onyx API endpoint** - Was using upload endpoint (404)
   - Fix: Found correct endpoint via OpenAPI: `/onyx-api/ingestion`

8. **Schema mismatch with Onyx** - Documents rejected
   - Set `source` field to `null`
   - Convert all metadata values to strings
   - Added `from_ingestion_api: true` flag

9. **HTTP 401 Invalid API key** - FIXED ✅
   - **Root Cause:** Extra whitespace/newlines in API key in .env file
   - **Fix:** Sanitized API key with `.strip()` and ensured clean .env file
   - **Note:** Header format is `Authorization: Bearer {key}` (NOT x-onyx-key)

10. **Timeouts during ingestion** - CPU embeddings slow
    - **Fix:** Increased timeout from 30s to 120s
    - **Fix:** Added retry logic with exponential backoff
    - **Fix:** Handle 429 rate limits and 5xx errors with retries

## Session 2025-12-11 Changes

### Code Changes Made

1. **`cli.py` - Refactored `send_to_onyx` function** (lines 216-344)
   - Added `timeout` parameter (default 120s for CPU embeddings)
   - Added `max_retries` parameter (default 3)
   - Added retry logic with exponential backoff
   - Added 429 rate limit handling with Retry-After support
   - Added 5xx server error retry
   - Added API key validation and sanitization (`.strip()`)
   - Safe debug logging (only shows first 4 chars of key)
   - Added `--verbose` flag to sync command

2. **Debug scripts added:**
   - `docker/test_onyx_auth.py` - Tests all auth header formats

### Git Commits Made:
- `fix: use x-onyx-key header for self-hosted Onyx authentication` (reverted)
- `debug: add API key logging to troubleshoot auth issue`
- `refactor: rewrite send_to_onyx with retry logic, rate limiting, and proper error handling`
- `fix: increase timeout to 120s for slow Onyx indexing`
- `debug: test all Onyx auth header formats`

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
│  - Retries      │
└────────┬────────┘
         │
         ▼ (onyx_default network)
┌─────────────────┐
│  Onyx API       │ (Docker: onyx-api_server-1:8080)
│  - Ingestion    │
│  - Embeddings   │ (CPU-based, ~0.8s per doc)
│  - Search       │
└─────────────────┘
```

## Verification

Documents are successfully ingesting. Onyx logs confirm:
```
Upserted 1 changed docs out of 1 total docs into the DB
embed_chunks took 0.766 seconds
```

## Next Steps

1. ✅ **Auth working** - Bearer token auth confirmed working
2. ✅ **Ingestion working** - Documents now ingesting to Onyx
3. **Let full sync complete** - ~2.5+ hours due to volume + CPU embeddings
4. **Verify search in Onyx UI** - Query for tickets/customers
5. **Add incremental sync** - Poll for changes instead of full sync each time

## Contact

- **Repo:** https://github.com/SilverWulf212/Onyx-RS-Bridge
- **RepairShopr Instance:** silverwulf.repairshopr.com
