import os
import shutil
import json
import yaml
from git import Repo
import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class CatalogGenerationError(Exception):
    def __init__(self, message: str, stderr: str):
        super().__init__(message)
        self.stderr = stderr

class CatalogGenerator:
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def get_workspace_path(self, owner: str, repo: str, pull_number: int) -> str:
        return os.path.join(self.cache_dir, f"{owner}_{repo}_pr{pull_number}")

    def generate(self, clone_url: str, owner: str, repo: str, sha: str, pull_number: int, service_base_url: str, pr_files: list[str] = None) -> str:
        workspace_path = self.get_workspace_path(owner, repo, pull_number)
        build_path = os.path.join(workspace_path, "build")
        sha_file = os.path.join(workspace_path, ".generated_sha")

        # Check if we already have the correct SHA generated
        if os.path.exists(build_path) and os.path.exists(sha_file):
            with open(sha_file, "r") as f:
                cached_sha = f.read().strip()
            if cached_sha == sha:
                logger.info(f"Using cached build for PR {pull_number} (SHA: {sha})")
                return build_path

        # If it exists but is old/invalid, clean it up
        if os.path.exists(workspace_path):
            logger.info(f"Removing outdated workspace {workspace_path}...")
            # We only remove the build and sha file so we can reuse the cloned repo if possible
            if os.path.exists(build_path):
                shutil.rmtree(build_path)
            if os.path.exists(sha_file):
                os.remove(sha_file)

        if not os.path.exists(workspace_path):
            logger.info(f"Cloning {clone_url} to {workspace_path}...")
            Repo.clone_from(clone_url, workspace_path)
        else:
            # Fetch latest to ensure we have the commit
            repo_obj = Repo(workspace_path)
            logger.info("Fetching latest from remote...")
            repo_obj.remotes.origin.fetch()
        
        repo_obj = Repo(workspace_path)
        logger.info(f"Checking out {sha}...")
        repo_obj.git.checkout(sha)

        # Process modified files for injection and command arguments
        pr_files = pr_files or []
        existing_pr_files = [f for f in pr_files if os.path.exists(os.path.join(workspace_path, f))]
        
        collections_files = [f for f in existing_pr_files if f.startswith("collections/")]
        indicator_files = [f for f in existing_pr_files if f.startswith("indicators/")]
        
        collections_in_indicators = set()
        modified_names_set = set()

        for f in indicator_files:
            name, ext = os.path.splitext(os.path.basename(f))
            modified_names_set.add(name)
            
            file_path = os.path.join(workspace_path, f)
            try:
                with open(file_path, 'r') as fh:
                    if ext.lower() == '.json':
                        data = json.load(fh)
                    else:
                        data = yaml.safe_load(fh)
                if isinstance(data, dict) and "Collections" in data:
                    for c in data["Collections"]:
                        collections_in_indicators.add(c)
            except Exception as e:
                logger.warning(f"Failed to read indicator file {f}: {e}")

        names_to_add = []
        for f in collections_files:
            name = os.path.splitext(os.path.basename(f))[0]
            modified_names_set.add(name)
            if name not in collections_in_indicators and name not in names_to_add:
                names_to_add.append(name)

        for f in indicator_files:
            name = os.path.splitext(os.path.basename(f))[0]
            if name not in names_to_add:
                names_to_add.append(name)

        modified_names = list(modified_names_set)

        logger.info(f"CLI arguments (modified_names): {modified_names}")
        logger.info(f"Keys to inject into catalog config: {names_to_add}")

        # Modify catalog configurations to override endpoint and inject new names
        self._update_catalogs_config(workspace_path, service_base_url, names_to_add)

        # If no relevant changes are detected, generate an empty catalog instead of a full build
        if not modified_names:
            logger.info("No relevant changes detected. Generating an empty catalog.")
            self._generate_empty_catalog(workspace_path, build_path, service_base_url)
            # Write the SHA to mark successful generation
            with open(sha_file, "w") as f:
                f.write(sha)
            return build_path

        # Run eodash_catalog
        logger.info(f"Generating catalog for specific collections/indicators: {modified_names}")
        
        cmd = ["eodash_catalog", "--outputpath", "build"] + modified_names
        
        # Ensure environment variables (like SH_INSTANCE_ID, SH_CLIENT_SECRET) are passed to the subprocess
        env = os.environ.copy()
        
        # Load repo-specific secrets if defined in REPO_SECRETS_JSON mapping
        repo_secrets_json = os.getenv("REPO_SECRETS_JSON")
        if repo_secrets_json:
            try:
                secrets_map = json.loads(repo_secrets_json)
                repo_full_name = f"{owner}/{repo}"
                repo_secrets = secrets_map.get(repo_full_name, {})
                if repo_secrets:
                    logger.info(f"Adding repo-specific secrets for {repo_full_name}: {list(repo_secrets.keys())}")
                    env.update(repo_secrets)
            except json.JSONDecodeError:
                logger.error("Failed to parse REPO_SECRETS_JSON environment variable. Ensure it is a valid JSON string.")

        logger.info(f"Running command: {' '.join(cmd)} in {workspace_path}...")
        try:
            subprocess.run(
                cmd,
                cwd=workspace_path,
                env=env,
                check=True,
                capture_output=True,
                text=True
            )
            # Write the SHA to mark successful generation
            with open(sha_file, "w") as f:
                f.write(sha)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running eodash_catalog: {e.stderr}")
            raise CatalogGenerationError("Catalog generation failed", e.stderr)

        return build_path

    def _generate_empty_catalog(self, workspace_path: str, build_path: str, service_base_url: str):
        """
        Generates a minimal STAC catalog when no collections or indicators are modified.
        """
        if not os.path.exists(build_path):
            os.makedirs(build_path)
        
        # Default info
        catalog_info = {
            "stac_version": "1.0.0",
            "type": "Catalog",
            "id": "empty-catalog",
            "title": "Empty Catalog",
            "description": "This catalog is empty because no changes were detected in the PR.",
            "links": []
        }
        
        # Try to find some info from existing catalog configurations in the repo
        catalogs_dir = os.path.join(workspace_path, "catalogs")
        if os.path.exists(catalogs_dir):
            for filename in os.listdir(catalogs_dir):
                if filename.endswith(".json") or filename.endswith(".yaml") or filename.endswith(".yml"):
                    file_path = os.path.join(catalogs_dir, filename)
                    try:
                        with open(file_path, 'r') as f:
                            if filename.endswith(".json"):
                                data = json.load(f)
                            else:
                                data = yaml.safe_load(f)
                        if isinstance(data, dict):
                            if "id" in data: catalog_info["id"] = data["id"]
                            if "title" in data: catalog_info["title"] = data["title"]
                            if "description" in data: catalog_info["description"] = data["description"]
                            # Use the first valid one we find
                            break
                    except Exception as e:
                        logger.warning(f"Failed to read catalog config {filename}: {e}")

        # Ensure links are correct
        # service_base_url should already end with / as ensured in main.py
        catalog_url = f"{service_base_url}catalog.json"
        catalog_info["links"] = [
            {
                "rel": "self",
                "href": catalog_url,
                "type": "application/json"
            },
            {
                "rel": "root",
                "href": catalog_url,
                "type": "application/json"
            }
        ]
        
        output_file = os.path.join(build_path, "catalog.json")
        with open(output_file, 'w') as f:
            json.dump(catalog_info, f, indent=2)
        logger.info(f"Generated empty catalog at {output_file}")

    def _update_catalogs_config(self, workspace_path: str, service_base_url: str, names_to_add: list[str]):
        catalogs_dir = os.path.join(workspace_path, "catalogs")
        if not os.path.exists(catalogs_dir):
            return

        for filename in os.listdir(catalogs_dir):
            if filename.endswith(".json") or filename.endswith(".yaml") or filename.endswith(".yml"):
                file_path = os.path.join(catalogs_dir, filename)
                with open(file_path, 'r') as f:
                    if filename.endswith(".json"):
                        data = json.load(f)
                    else:
                        data = yaml.safe_load(f)
                
                changed = False

                # Update endpoint
                if isinstance(data, dict) and "endpoint" in data:
                    data["endpoint"] = service_base_url
                    changed = True
                
                # Inject new collections/indicators
                if isinstance(data, dict) and names_to_add:
                    if "collections" not in data:
                        data["collections"] = []
                    
                    existing_entries = set(data["collections"])
                    for name in names_to_add:
                        if name not in existing_entries:
                            data["collections"].append(name)
                            existing_entries.add(name)
                            changed = True
                    
                if changed:
                    with open(file_path, 'w') as f:
                        if filename.endswith(".json"):
                            json.dump(data, f, indent=2)
                        else:
                            yaml.dump(data, f)
