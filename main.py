from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from github import GitHubClient
from generator import CatalogGenerator, CatalogGenerationError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Catalog Generator Service")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
CACHE_DIR = os.getenv("CATALOG_CACHE_DIR", "/tmp/catalog_cache")

github_client = GitHubClient(token=GITHUB_TOKEN)
generator = CatalogGenerator(cache_dir=CACHE_DIR)

@app.get("/{owner}/{repo}/pull/{number}/{path:path}")
def get_catalog_file(owner: str, repo: str, number: int, path: str, request: Request):
    """
    Dynamically generates and serves STAC catalog files for a specific GitHub Pull Request.
    """
    # Determine the service base URL for this PR to ensure STAC links are correct
    base_url = str(request.base_url)
    # Ensure base_url ends with / if it doesn't, but base_url from request usually has it
    if not base_url.endswith("/"):
        base_url += "/"
    service_pr_url = f"{base_url}{owner}/{repo}/pull/{number}/"

    logger.info(f"Request for {path} in {owner}/{repo} PR #{number}")

    try:
        # 1. Fetch PR information from GitHub
        pr_info = github_client.get_pr_info(owner, repo, number)
        head_info = github_client.get_head_info(pr_info)
        sha = head_info["sha"]
        clone_url = head_info["clone_url"]

        # Fetch modified files in the PR
        pr_files = github_client.get_pr_files(owner, repo, number)
        
        logger.info(f"PR #{number} changed {len(pr_files)} files: {pr_files}")

        # 2. Generate or retrieve the catalog from cache
        build_dir = generator.generate(
            clone_url=clone_url,
            owner=owner,
            repo=repo,
            sha=sha,
            pull_number=number,
            service_base_url=service_pr_url,
            pr_files=pr_files
        )

        # eodash_catalog often outputs into a subdirectory named after the catalog ID.
        # If build_dir contains exactly one subdirectory and no other files, we should use that subdirectory.
        if os.path.exists(build_dir):
            items = os.listdir(build_dir)
            if len(items) == 1:
                single_item_path = os.path.join(build_dir, items[0])
                if os.path.isdir(single_item_path):
                    build_dir = single_item_path

        # 3. Serve the requested file
        # If path is empty, default to catalog.json? 
        # Actually path is required by the route.
        
        file_path = os.path.join(build_dir, path)
        
        # Special case: if catalog.json is requested but not found, 
        # look for any .json file in the build root.
        if path == "catalog.json" and not os.path.exists(file_path):
            json_files = [f for f in os.listdir(build_dir) if f.endswith(".json") and os.path.isfile(os.path.join(build_dir, f))]
            if json_files:
                file_path = os.path.join(build_dir, json_files[0])
                logger.info(f"catalog.json not found, falling back to {json_files[0]}")

        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            raise HTTPException(status_code=404, detail=f"File {path} not found in generated catalog")

        return FileResponse(file_path)

    except CatalogGenerationError as e:
        logger.error("Catalog generation subprocess failed.")
        # Parse the stderr to make it more readable in the JSON response
        stderr_lines = [line for line in e.stderr.strip().split('\n') if line]
        error_summary = stderr_lines[-1] if stderr_lines else "Unknown error occurred during catalog generation."
        
        raise HTTPException(
            status_code=500, 
            detail={
                "message": "Catalog generation failed.",
                "error_summary": error_summary,
                "traceback": stderr_lines
            }
        )
    except Exception as e:
        logger.exception("Error processing request")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {
        "message": "Catalog Generator Service is running.",
        "usage": "/{owner}/{repo}/pull/{number}/catalog.json",
        "example": "/GTIF-Austria/public-catalog/pull/135/catalog.json"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
