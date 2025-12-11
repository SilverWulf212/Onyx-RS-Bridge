#!/usr/bin/env python3
"""Check the expected schema for /onyx-api/ingestion endpoint."""
import httpx
import os
import json

url = os.environ.get('ONYX_API_URL', 'http://onyx-api_server-1:8080')
key = os.environ.get('ONYX_API_KEY', '')

headers = {'Authorization': f'Bearer {key}'}

r = httpx.get(f'{url}/openapi.json', headers=headers)
d = r.json()

# Find the ingestion endpoint schema
ingestion = d.get('paths', {}).get('/onyx-api/ingestion', {})

print("=== /onyx-api/ingestion ===")
print()

if 'post' in ingestion:
    post = ingestion['post']
    print(f"Summary: {post.get('summary', 'N/A')}")
    print(f"Description: {post.get('description', 'N/A')}")
    print()

    # Get request body schema
    req_body = post.get('requestBody', {})
    if req_body:
        print("Request Body:")
        content = req_body.get('content', {})
        for content_type, schema_info in content.items():
            print(f"  Content-Type: {content_type}")
            schema = schema_info.get('schema', {})
            if '$ref' in schema:
                ref = schema['$ref'].split('/')[-1]
                print(f"  Schema: {ref}")
                # Look up the schema definition
                schema_def = d.get('components', {}).get('schemas', {}).get(ref, {})
                print(f"  Properties: {json.dumps(schema_def, indent=4)[:2000]}")
            else:
                print(f"  Schema: {json.dumps(schema, indent=4)[:1000]}")

if 'get' in ingestion:
    get = ingestion['get']
    print()
    print("GET also available:")
    print(f"  Summary: {get.get('summary', 'N/A')}")
