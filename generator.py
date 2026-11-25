import os
import shutil
import json
try:
    import yaml
except ImportError:
    yaml = None
from git import Repo
import subprocess
import logging
from typing import Optional
import threading

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
        self._locks = {}
        self._locks_lock = threading.Lock()

    def _get_lock(self, owner: str, repo: str, pull_number: int):
        key = (owner, repo, pull_number)
        with self._locks_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def resolve_modified_names(self, workspace_path: str, pr_files: list[str]) -> tuple[list[str], list[str]]:
        """
        Determines the list of collection/indicator names to generate (modified_names)
        and names to inject into catalog configs (names_to_add) based on PR file changes.

        Rules:
        1. If an indicator file is modified:
           - Include only the indicator name (do NOT include its child collections unless
             a child collection is explicitly listed in existing catalog configs).
        2. If a collection file is modified:
           - Check if the collection is explicitly listed in any existing catalog config.
             If so, treat it as a standalone collection.
           - Otherwise, check if it belongs to any indicator(s).
             If it belongs to an indicator, include the parent indicator name(s) instead.
           - If it doesn't belong to any indicator, include the collection name.
        3. If a catalog configuration file is modified:
           - Include all collections listed in that catalog config.
        """
        pr_files = pr_files or []
        existing_pr_files = [f for f in pr_files if os.path.exists(os.path.join(workspace_path, f))]

        collections_files = [f for f in existing_pr_files if f.startswith("collections/")]
        indicator_files = [f for f in existing_pr_files if f.startswith("indicators/")]
        catalog_files = [f for f in existing_pr_files if f.startswith("catalogs/")]

        # Read existing catalog configuration files to know which collections/indicators are pre-defined
        catalog_defined_collections = set()
        catalogs_dir = os.path.join(workspace_path, "catalogs")
        if os.path.exists(catalogs_dir):
            for cat_filename in os.listdir(catalogs_dir):
                if cat_filename.endswith((".json", ".yaml", ".yml")):
                    cat_path = os.path.join(catalogs_dir, cat_filename)
                    try:
                        with open(cat_path, 'r') as fh:
                            if cat_filename.endswith('.json'):
                                cat_data = json.load(fh)
                            else:
                                cat_data = yaml.safe_load(fh)
                        if isinstance(cat_data, dict) and "collections" in cat_data:
                            for c in cat_data["collections"]:
                                catalog_defined_collections.add(c)
                    except Exception as e:
                        logger.warning(f"Failed to read catalog config {cat_filename}: {e}")

        # Map each collection to parent indicator(s) by scanning indicators directory
        collection_to_indicators = {}
        indicators_dir = os.path.join(workspace_path, "indicators")
        if os.path.exists(indicators_dir):
            for ind_filename in os.listdir(indicators_dir):
                if ind_filename.endswith((".json", ".yaml", ".yml")):
                    ind_path = os.path.join(indicators_dir, ind_filename)
                    ind_name = os.path.splitext(ind_filename)[0]
                    try:
                        with open(ind_path, 'r') as fh:
                            if ind_filename.endswith('.json'):
                                ind_data = json.load(fh)
                            else:
                                ind_data = yaml.safe_load(fh)
                        if isinstance(ind_data, dict) and "Collections" in ind_data:
                            for child_coll in ind_data["Collections"]:
                                collection_to_indicators.setdefault(child_coll, set()).add(ind_name)
                    except Exception as e:
                        logger.warning(f"Failed to read indicator file {ind_filename}: {e}")

        modified_names_set = set()
        names_to_add_set = set()

        # Rule 1: Process modified indicator files
        for f in indicator_files:
            ind_name = os.path.splitext(os.path.basename(f))[0]
            modified_names_set.add(ind_name)
            names_to_add_set.add(ind_name)

        # Rule 2: Process modified collection files
        for f in collections_files:
            coll_name = os.path.splitext(os.path.basename(f))[0]
            if coll_name in catalog_defined_collections:
                modified_names_set.add(coll_name)
                names_to_add_set.add(coll_name)
            elif coll_name in collection_to_indicators:
                for parent_ind in collection_to_indicators[coll_name]:
                    modified_names_set.add(parent_ind)
                    names_to_add_set.add(parent_ind)
            else:
                modified_names_set.add(coll_name)
                names_to_add_set.add(coll_name)

        # Rule 3: If catalog config files were modified, rebuild all items listed in catalog config
        if catalog_files:
            for c in catalog_defined_collections:
                modified_names_set.add(c)
                names_to_add_set.add(c)

        return list(modified_names_set), list(names_to_add_set)

    def get_workspace_path(self, owner: str, repo: str, pull_number: int) -> str:
        return os.path.join(self.cache_dir, f"{owner}_{repo}_pr{pull_number}")

    def generate(self, clone_url: str, owner: str, repo: str, sha: str, pull_number: int, service_base_url: str, pr_files: list[str] = None, force_refresh: bool = False) -> str:
        workspace_path = self.get_workspace_path(owner, repo, pull_number)
        build_path = os.path.join(workspace_path, "build")
        sha_file = os.path.join(workspace_path, ".generated_sha")

        # Check if we already have the correct SHA generated (and not forced refresh)
        if not force_refresh and os.path.exists(build_path) and os.path.exists(sha_file):
            with open(sha_file, "r") as f:
                cached_sha = f.read().strip()
            if cached_sha == sha:
                logger.info(f"Using cached build for PR {pull_number} (SHA: {sha})")
                return build_path

        # Acquire lock for this specific PR to avoid concurrent builds
        with self._get_lock(owner, repo, pull_number):
            # Re-check cache after acquiring lock (and not forced refresh)
            if not force_refresh and os.path.exists(build_path) and os.path.exists(sha_file):
                with open(sha_file, "r") as f:
                    cached_sha = f.read().strip()
                if cached_sha == sha:
                    logger.info(f"Using cached build for PR {pull_number} (SHA: {sha})")
                    return build_path

            # If it exists but is old/invalid/refresh-forced, clean it up
            if os.path.exists(workspace_path):
                if force_refresh:
                    logger.info(f"Force-refresh requested for PR {pull_number}...")
                else:
                    logger.info(f"Removing outdated build files in {workspace_path}...")
                
                if os.path.exists(build_path):
                    shutil.rmtree(build_path)
                if os.path.exists(sha_file):
                    os.remove(sha_file)

            if not os.path.exists(workspace_path):
                logger.info(f"Cloning {clone_url} to {workspace_path}...")
                repo_obj = Repo.clone_from(clone_url, workspace_path)
            else:
                # Fetch latest to ensure we have the commit
                repo_obj = Repo(workspace_path)
                logger.info("Fetching latest from remote...")
                try:
                    # Reset any local changes from previous runs to avoid checkout conflicts
                    repo_obj.git.reset('--hard')
                    repo_obj.git.clean('-fd')
                except Exception as e:
                    logger.warning(f"Failed to clean/reset repo: {e}")
                repo_obj.remotes.origin.fetch()
            
            logger.info(f"Checking out {sha}...")
            # Use force=True to ensure we overwrite any remaining local changes
            repo_obj.git.checkout(sha, force=True)

            # Process modified files for injection and command arguments
            modified_names, names_to_add = self.resolve_modified_names(workspace_path, pr_files)

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
            
            # Add -gp flag to generate Parquet files for better performance with large collections
            cmd = ["eodash_catalog", "--outputpath", "build", "-gp"] + modified_names
            
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
                res = subprocess.run(
                    cmd,
                    cwd=workspace_path,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                # Perform strict validation on eodash_catalog output and logs
                self._check_eodash_catalog_errors(build_path, modified_names, res.stdout, res.stderr)

                # Write the SHA to mark successful generation only if check passed
                with open(sha_file, "w") as f:
                    f.write(sha)
            except subprocess.CalledProcessError as e:
                logger.error(f"Error running eodash_catalog: {e.stderr}")
                raise CatalogGenerationError("Catalog generation failed", e.stderr)

            return build_path

    def _check_eodash_catalog_errors(self, build_path: str, modified_names: list[str], stdout: str, stderr: str):
        """
        Inspects eodash_catalog output logs and build directory to detect errors.
        If an error occurred during catalog generation, raises CatalogGenerationError.
        """
        combined_output = (stdout or "") + "\n" + (stderr or "")
        
        # 1. Search for error indicators in stdout/stderr
        error_keywords = [
            "Error processing indicator",
            "Error processing collection",
            "Error processing",
            "[error",
            "level='error'",
            "level=\"error\"",
            "Traceback (most recent call last):",
        ]
        
        found_error_lines = []
        for line in combined_output.splitlines():
            if any(keyword in line for keyword in error_keywords):
                found_error_lines.append(line.strip())

        if found_error_lines:
            error_details = "\n".join(found_error_lines)
            logger.error(f"Detected eodash_catalog error: {error_details}")
            raise CatalogGenerationError("Catalog generation failed due to catalog creation errors.", combined_output)

        # 2. Check if requested items were actually generated in build_path
        catalog_root = build_path
        if os.path.exists(build_path):
            subdirs = [os.path.join(build_path, d) for d in os.listdir(build_path) if os.path.isdir(os.path.join(build_path, d))]
            if len(subdirs) == 1:
                catalog_root = subdirs[0]

        root_catalog_file = os.path.join(catalog_root, "catalog.json")
        if not os.path.exists(root_catalog_file):
            raise CatalogGenerationError("Catalog generation failed: catalog.json was not created.", combined_output)

        # Verify that catalog.json contains links for requested modified_names if modified_names was non-empty
        if modified_names:
            try:
                with open(root_catalog_file, 'r') as fh:
                    cat_data = json.load(fh)
                links = cat_data.get("links", [])
                child_hrefs = [l.get("href", "") for l in links if l.get("rel") in ["child", "item"]]
                
                matched = False
                for name in modified_names:
                    if any(name in href for href in child_hrefs):
                        matched = True
                        break
                
                if not matched and child_hrefs == []:
                    logger.error(f"Generated catalog at {root_catalog_file} contains no child links for {modified_names}")
                    raise CatalogGenerationError(
                        f"Catalog generation failed: no child items created for requested items {modified_names}.",
                        combined_output
                    )
            except CatalogGenerationError:
                raise
            except Exception as e:
                logger.warning(f"Failed to inspect generated catalog.json for verification: {e}")

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
