# Project Instructions - Catalog Generator Service

## Tech Stack
- **Framework:** FastAPI
- **Language:** Python 3.11+
- **Core Library:** `eodash_catalog`
- **Deployment:** Docker

## Architecture
- The service acts as a proxy/generator for STAC catalogs.
- It must handle GitHub PR URLs and branch information to fetch the correct configuration.
- Responses should follow the STAC specification.

## Development Workflow
- Use `pytest` for testing.
- Follow PEP 8 style guidelines.
- Ensure all endpoints are documented via FastAPI's OpenAPI (Swagger) UI.

## Conventions
- Use type hints for all function signatures.
- Log important events and errors.
- Cache generated catalogs if possible to improve performance.
