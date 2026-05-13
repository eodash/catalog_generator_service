import requests
from typing import Dict, Any

class GitHubClient:
    def __init__(self, token: str = None):
        self.token = token
        self.base_url = "https://api.github.com"

    def _get_headers(self):
        headers = {}
        if self.token:
            # Strip to ensure no accidental newlines from env vars, and use Bearer
            headers["Authorization"] = f"Bearer {self.token.strip()}"
        return headers

    def get_pr_info(self, owner: str, repo: str, pull_number: int) -> Dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        
        response = requests.get(url, headers=self._get_headers())
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"GitHub API Error for {url}: {response.status_code} - {response.text}") from e
        return response.json()

    def get_head_info(self, pr_info: Dict[str, Any]) -> Dict[str, str]:
        return {
            "ref": pr_info["head"]["ref"],
            "sha": pr_info["head"]["sha"],
            "clone_url": pr_info["head"]["repo"]["clone_url"]
        }

    def get_pr_files(self, owner: str, repo: str, pull_number: int) -> list[str]:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/files"
        headers = self._get_headers()
        
        files = []
        params = {"per_page": 100, "page": 1}
        while True:
            response = requests.get(url, headers=headers, params=params)
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                raise Exception(f"GitHub API Error for {url}: {response.status_code} - {response.text}") from e
            page_files = response.json()
            if not page_files:
                break
            files.extend([f["filename"] for f in page_files])
            if "next" not in response.links:
                break
            params["page"] += 1
        return files
