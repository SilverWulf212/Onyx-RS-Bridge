#!/usr/bin/env python3
"""Check TextSection and DocumentSource schemas."""
import httpx
import os
import json

url = os.environ.get('ONYX_API_URL', 'http://onyx-api_server-1:8080')
key = os.environ.get('ONYX_API_KEY', '')

headers = {'Authorization': f'Bearer {key}'}

r = httpx.get(f'{url}/openapi.json', headers=headers)
d = r.json()

schemas = d.get('components', {}).get('schemas', {})

print("=== TextSection Schema ===")
print(json.dumps(schemas.get('TextSection', {}), indent=2))

print()
print("=== DocumentSource Schema (enum values) ===")
doc_source = schemas.get('DocumentSource', {})
print(json.dumps(doc_source, indent=2))

print()
print("=== BasicExpertInfo Schema ===")
print(json.dumps(schemas.get('BasicExpertInfo', {}), indent=2))
