#!/usr/bin/env python3
"""Probe Onyx API to find available endpoints."""
import httpx
import os

url = os.environ.get('ONYX_API_URL', 'http://onyx-api_server-1:8080')
key = os.environ.get('ONYX_API_KEY', '')

print(f"Probing Onyx at: {url}")
print(f"API Key: {key[:20]}..." if key else "API Key: NOT SET")
print()

headers = {'Authorization': f'Bearer {key}'}

endpoints = [
    '/openapi.json',
    '/docs',
    '/api/v1',
    '/api',
    '/health',
    '/api/v1/manage/connector',
    '/api/v1/manage/admin/connector',
    '/api/v1/document',
    '/api/v1/indexing',
]

with httpx.Client(timeout=10) as client:
    for ep in endpoints:
        try:
            r = client.get(f'{url}{ep}', headers=headers)
            print(f'{ep}: {r.status_code}')
            if r.status_code == 200 and len(r.text) < 300:
                print(f'  -> {r.text[:200]}')
        except Exception as e:
            print(f'{ep}: ERROR - {e}')
