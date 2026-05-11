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

### Local Development

For easier development and testing, you can run the service directly without Docker.

#### Prerequisites
- **Python 3.11+**
- **Git**: Required for cloning repositories from GitHub.

#### 1. Set up a Virtual Environment
It is recommended to use a virtual environment to manage dependencies:

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
# .\venv\Scripts\activate
```

#### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 3. Run the Service
You can use `uvicorn` to run the service with auto-reload enabled for development:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The service will be available at `http://127.0.0.1:8000`. You can access the API documentation at `http://127.0.0.1:8000/docs`.
