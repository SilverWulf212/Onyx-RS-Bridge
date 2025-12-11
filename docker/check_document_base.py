#!/usr/bin/env python3
"""Check the DocumentBase schema that Onyx expects."""
import httpx
import os
import json

url = os.environ.get('ONYX_API_URL', 'http://onyx-api_server-1:8080')
key = os.environ.get('ONYX_API_KEY', '')

headers = {'Authorization': f'Bearer {key}'}

r = httpx.get(f'{url}/openapi.json', headers=headers)
d = r.json()

schemas = d.get('components', {}).get('schemas', {})

print("=== DocumentBase Schema ===")
print()
doc_base = schemas.get('DocumentBase', {})
print(json.dumps(doc_base, indent=2))

print()
print("=== Section Schema (if referenced) ===")
section = schemas.get('Section', {})
if section:
    print(json.dumps(section, indent=2))
