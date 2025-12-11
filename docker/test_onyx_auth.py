#!/usr/bin/env python3
"""
Debug script to test Onyx API authentication.
Run inside the container: cat docker/test_onyx_auth.py | docker exec -i rs-onyx-connector python3
"""
import os
import httpx

onyx_url = os.environ.get('ONYX_API_URL', 'http://onyx-api_server-1:8080')
api_key = os.environ.get('ONYX_API_KEY', '')

print(f"=== Onyx Auth Debug ===")
print(f"URL: {onyx_url}")
print(f"Key (first 10 chars): {api_key[:10]}..." if len(api_key) > 10 else "No key found!")
print()

# Test 1: OpenAPI spec (no auth required usually)
print("Test 1: Fetching /openapi.json (no auth)...")
try:
    r = httpx.get(f"{onyx_url}/openapi.json", timeout=10)
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        print("  ✓ Onyx is reachable")
except Exception as e:
    print(f"  ✗ Error: {e}")
print()

# Test 2: Try /api/user (authenticated endpoint)
print("Test 2: Fetching /api/user (with Bearer auth)...")
headers = {"Authorization": f"Bearer {api_key}"}
try:
    r = httpx.get(f"{onyx_url}/api/user", headers=headers, timeout=10)
    print(f"  Status: {r.status_code}")
    print(f"  Response: {r.text[:200]}")
except Exception as e:
    print(f"  ✗ Error: {e}")
print()

# Test 3: Try with x-onyx-key header
print("Test 3: Fetching /api/user (with x-onyx-key header)...")
headers = {"x-onyx-key": api_key}
try:
    r = httpx.get(f"{onyx_url}/api/user", headers=headers, timeout=10)
    print(f"  Status: {r.status_code}")
    print(f"  Response: {r.text[:200]}")
except Exception as e:
    print(f"  ✗ Error: {e}")
print()

# Test 4: Check if /onyx-api/ingestion is even listed in OpenAPI
print("Test 4: Checking if /onyx-api/ingestion exists...")
try:
    r = httpx.get(f"{onyx_url}/openapi.json", timeout=10)
    if r.status_code == 200:
        data = r.json()
        paths = data.get('paths', {})
        ingestion = paths.get('/onyx-api/ingestion')
        if ingestion:
            print("  ✓ Endpoint exists")
            # Check what security it expects
            post_info = ingestion.get('post', {})
            security = post_info.get('security', [])
            print(f"  Security requirements: {security}")
        else:
            print("  ✗ Endpoint NOT FOUND in OpenAPI spec!")
            # List available endpoints that contain 'ingestion'
            matching = [p for p in paths.keys() if 'ingestion' in p.lower()]
            if matching:
                print(f"  Similar endpoints: {matching}")
except Exception as e:
    print(f"  ✗ Error: {e}")
print()

# Test 5: Try the ingestion endpoint with minimal payload
print("Test 5: Testing ingestion endpoint...")
headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
payload = {
    "document": {
        "id": "test_doc_1",
        "semantic_identifier": "Test Document",
        "sections": [{"text": "This is a test."}],
        "source": "file",
        "metadata": {}
    }
}
try:
    r = httpx.post(f"{onyx_url}/onyx-api/ingestion", json=payload, headers=headers, timeout=10)
    print(f"  Status: {r.status_code}")
    print(f"  Response: {r.text[:300]}")
except Exception as e:
    print(f"  ✗ Error: {e}")
