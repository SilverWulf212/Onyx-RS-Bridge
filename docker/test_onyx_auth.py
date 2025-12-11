#!/usr/bin/env python3
"""
Debug script to test ALL Onyx API authentication methods.
Run: cat docker/test_onyx_auth.py | docker exec -i rs-onyx-connector python3
"""
import os
import httpx

onyx_url = os.environ.get('ONYX_API_URL', 'http://onyx-api_server-1:8080')
api_key = os.environ.get('ONYX_API_KEY', '')

print(f"=== Onyx Auth Debug v2 ===")
print(f"URL: {onyx_url}")
print(f"Key (first 10 chars): {api_key[:10]}..." if len(api_key) > 10 else "No key!")
print()

test_payload = {
    "document": {
        "id": "test_doc_1",
        "semantic_identifier": "Test Document",
        "sections": [{"text": "This is a test."}],
        "source": "file",
        "metadata": {},
        "from_ingestion_api": True
    }
}

endpoint = f"{onyx_url}/onyx-api/ingestion"

# Test different auth header combinations
auth_methods = [
    ("Authorization: Bearer", {"Authorization": f"Bearer {api_key}"}),
    ("X-Onyx-Authorization: Bearer", {"X-Onyx-Authorization": f"Bearer {api_key}"}),
    ("x-onyx-key only", {"x-onyx-key": api_key}),
    ("Both Authorization + x-onyx-key", {"Authorization": f"Bearer {api_key}", "x-onyx-key": api_key}),
    ("No auth (baseline)", {}),
]

for name, headers in auth_methods:
    headers["Content-Type"] = "application/json"
    print(f"Test: {name}")
    try:
        r = httpx.post(endpoint, json=test_payload, headers=headers, timeout=10)
        print(f"  Status: {r.status_code}")
        print(f"  Response: {r.text[:150]}")
    except Exception as e:
        print(f"  Error: {e}")
    print()

# Also check what endpoints exist
print("=== Available ingestion-related endpoints ===")
try:
    r = httpx.get(f"{onyx_url}/openapi.json", timeout=10)
    if r.status_code == 200:
        data = r.json()
        paths = data.get('paths', {})
        for path in sorted(paths.keys()):
            if 'ingestion' in path.lower() or 'document' in path.lower() or 'onyx-api' in path.lower():
                methods = list(paths[path].keys())
                print(f"  {path}: {methods}")
except Exception as e:
    print(f"  Error: {e}")
