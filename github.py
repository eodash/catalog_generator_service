import requests
from typing import Dict, Any

class GitHubClient:
    def __init__(self, token: str = None):
        self.token = token
        self.base_url = "https://api.github.com"

    def get_pr_info(self, owner: str, repo: str, pull_number: int) -> Dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        headers = {}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_head_info(self, pr_info: Dict[str, Any]) -> Dict[str, str]:
        return {
            "ref": pr_info["head"]["ref"],
            "sha": pr_info["head"]["sha"],
            "clone_url": pr_info["head"]["repo"]["clone_url"]
        }

    def get_pr_files(self, owner: str, repo: str, pull_number: int) -> list[str]:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/files"
        headers = {}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        
        files = []
        params = {"per_page": 100, "page": 1}
        while True:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            page_files = response.json()
            if not page_files:
                break
            files.extend([f["filename"] for f in page_files])
            if "next" not in response.links:
                break
            params["page"] += 1
        return files
