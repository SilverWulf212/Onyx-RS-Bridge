# Developer Handoff: Onyx-RS-Bridge

**Last Updated:** 2025-12-11 02:45 UTC

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

## Current Issue to Debug

The Onyx ingestion is newly added in `cli.py:send_to_onyx()`. It's using this endpoint:
```
POST /api/v1/manage/admin/connector/file/upload
```

This may not be the correct Onyx endpoint. Need to:
1. Check Onyx API docs for correct ingestion endpoint
2. Verify the payload format Onyx expects
3. Test with a single document first

## Onyx API Investigation Needed

The current `send_to_onyx()` function sends:
```python
payload = {"document": doc.to_dict()}
```

To endpoint: `/api/v1/manage/admin/connector/file/upload`

This is likely wrong. Onyx ingestion typically works via:
1. **Native connector** - Register as a connector in Onyx codebase
2. **Ingestion API** - Push documents to a specific endpoint
3. **File upload** - Upload files that Onyx processes

Need to check:
- Onyx source code or API docs for correct endpoint
- Required authentication headers
- Expected payload format

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
