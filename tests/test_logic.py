import pytest
from github import GitHubClient

def test_github_head_info():
    client = GitHubClient()
    mock_pr_info = {
        "head": {
            "ref": "feature-branch",
            "sha": "abc123sha",
            "repo": {
                "clone_url": "https://github.com/owner/repo.git"
            }
        }
    }
    head_info = client.get_head_info(mock_pr_info)
    assert head_info["ref"] == "feature-branch"
    assert head_info["sha"] == "abc123sha"
    assert head_info["clone_url"] == "https://github.com/owner/repo.git"

def test_override_endpoints_logic(tmp_path):
    # Mocking the override_endpoints logic from generator.py
    from generator import CatalogGenerator
    import json
    import os

    catalogs_dir = tmp_path / "catalogs"
    catalogs_dir.mkdir()
    catalog_file = catalogs_dir / "test.json"
    
    original_data = {
        "id": "test",
        "endpoint": "http://original.com"
    }
    with open(catalog_file, 'w') as f:
        json.dump(original_data, f)
    
    generator = CatalogGenerator(cache_dir=str(tmp_path / "cache"))
    generator._override_endpoints(str(tmp_path), "http://service.com/")
    
    with open(catalog_file, 'r') as f:
        updated_data = json.load(f)
    
    assert updated_data["endpoint"] == "http://service.com/"

