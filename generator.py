import os
import shutil
import json
import yaml
from git import Repo
import subprocess
from typing import Optional

class CatalogGenerator:
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def get_workspace_path(self, owner: str, repo: str, sha: str) -> str:
        return os.path.join(self.cache_dir, f"{owner}_{repo}_{sha}")

    def generate(self, clone_url: str, owner: str, repo: str, sha: str, service_base_url: str) -> str:
        workspace_path = self.get_workspace_path(owner, repo, sha)
        build_path = os.path.join(workspace_path, "build")

        if os.path.exists(build_path):
            # Already generated
            return build_path

        if not os.path.exists(workspace_path):
            print(f"Cloning {clone_url} to {workspace_path}...")
            Repo.clone_from(clone_url, workspace_path)
        
        repo_obj = Repo(workspace_path)
        print(f"Checking out {sha}...")
        repo_obj.git.checkout(sha)

        # Modify catalog configurations to override endpoint
        self._override_endpoints(workspace_path, service_base_url)

        # Run eodash_catalog
        # We'll use subprocess to run the CLI as it's easier to ensure all environment vars and paths are correct
        print(f"Running eodash_catalog build in {workspace_path}...")
        try:
            # We assume eodash_catalog is in the PATH
            # Command: eodash_catalog --catalogspath catalogs --collectionspath collections --indicatorspath indicators --outputpath build
            subprocess.run(
                ["eodash_catalog", "--outputpath", "build"],
                cwd=workspace_path,
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error running eodash_catalog: {e.stderr}")
            raise Exception(f"Catalog generation failed: {e.stderr}")

        return build_path

    def _override_endpoints(self, workspace_path: str, service_base_url: str):
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
                
                # Update endpoint
                if isinstance(data, dict) and "endpoint" in data:
                    data["endpoint"] = service_base_url
                    
                    with open(file_path, 'w') as f:
                        if filename.endswith(".json"):
                            json.dump(data, f, indent=2)
                        else:
                            yaml.dump(data, f)
                elif isinstance(data, list):
                    # Some catalogs might be a list of catalogs? Unlikely for eodash_catalog main config
                    pass
