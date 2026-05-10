# Design Document - Catalog Generator Service

## Goal
Provide a dynamic STAC catalog preview for GitHub Pull Requests.

## Proposed API

### Endpoint Structure
`/{owner}/{repo}/pull/{number}/{path:path}`

Example:
`http://service-url/GTIF-Austria/public-catalog/pull/135/catalog.json`

### Internal Logic
1. **Request Received:** `GET /GTIF-Austria/public-catalog/pull/135/catalog.json`
2. **Fetch PR Info:**
   - Use GitHub API to find the branch/commit for PR 135 in `GTIF-Austria/public-catalog`.
3. **Workspace Preparation:**
   - Clone/Fetch the repo at the specific commit.
   - Cache the workspace to avoid re-cloning for every request in the same PR.
4. **Generation:**
   - Run `eodash_catalog` build.
   - The root URL for the catalog must be set to the service's endpoint for this PR: `http://service-url/GTIF-Austria/public-catalog/pull/135/`.
5. **Serve Response:**
   - Return the content of the requested file (e.g., `catalog.json`).

## Technical Components
- **FastAPI:** Web framework.
- **GitPython / Subprocess:** To handle repository fetching.
- **eodash_catalog:** Core logic for STAC generation.
- **Disk Caching:** Store clones and generated catalogs in a temporary directory with a TTL or LRU policy.

## Challenges & Solutions
- **Performance:** Cloning can be slow. Use `git clone --depth 1` and cache the results.
- **Link Integrity:** Ensure `eodash_catalog` generates links that point back to the service.
- **Concurrency:** Multiple requests for the same PR should share the same build if possible.

## Dockerization
- Base image: `python:3.11-slim`
- Install `git` and necessary dependencies.
- Expose port 8000.
