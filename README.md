# Catalog Generator Service

A FastAPI-based service that dynamically generates STAC catalog responses based on GitHub Pull Requests using `eodash_catalog`.

## Overview

This service mocks a STAC endpoint. When requested with a GitHub PR URL, it:
1. Fetches the changed catalog configuration files from the PR.
2. Uses `eodash_catalog` to generate the STAC JSON responses on the fly.
3. Serves these responses to allow instant previewing in a STAC browser.

## Getting Started

### Prerequisites
- Docker
- Python 3.11+ (for local development)

### Configuration
The service can be configured using environment variables:
- `GITHUB_TOKEN`: (Optional) GitHub Personal Access Token for higher rate limits.
- `CATALOG_CACHE_DIR`: Directory where repositories and generated catalogs are cached (default: `/tmp/catalog_cache`).

### Running with Docker
```bash
docker build -t catalog-generator-service .
docker run -p 8000:8000 catalog-generator-service
```
