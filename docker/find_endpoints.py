#!/usr/bin/env python3
"""Find relevant Onyx API endpoints from OpenAPI spec."""
import httpx
import os
import json

url = os.environ.get('ONYX_API_URL', 'http://onyx-api_server-1:8080')
key = os.environ.get('ONYX_API_KEY', '')

headers = {'Authorization': f'Bearer {key}'}

r = httpx.get(f'{url}/openapi.json', headers=headers)
d = r.json()

print("=== RELEVANT ENDPOINTS ===")
print()

keywords = ['document', 'ingest', 'index', 'connector', 'upload', 'file', 'seed']

for path in sorted(d.get('paths', {}).keys()):
    if any(kw in path.lower() for kw in keywords):
        methods = list(d['paths'][path].keys())
        print(f"{', '.join(m.upper() for m in methods):12} {path}")

        # Show POST endpoints details
        if 'post' in d['paths'][path]:
            post_info = d['paths'][path]['post']
            summary = post_info.get('summary', '')
            if summary:
                print(f"             -> {summary}")
