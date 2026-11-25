try:
    import pytest
except ImportError:
    pytest = None
import sys
import os

# Add the project root to the Python path so modules can be found
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
    generator._update_catalogs_config(str(tmp_path), "http://service.com/", [])
    
    with open(catalog_file, 'r') as f:
        updated_data = json.load(f)
    
    assert updated_data["endpoint"] == "http://service.com/"

def test_resolve_modified_names_indicator_change(tmp_path):
    from generator import CatalogGenerator
    import json

    indicators_dir = tmp_path / "indicators"
    indicators_dir.mkdir()
    ind_file = indicators_dir / "my_indicator.json"
    ind_data = {
        "Name": "my_indicator",
        "Collections": ["child_coll_1", "child_coll_2"]
    }
    with open(ind_file, 'w') as f:
        json.dump(ind_data, f)

    generator = CatalogGenerator(cache_dir=str(tmp_path / "cache"))
    pr_files = ["indicators/my_indicator.json"]

    modified_names, names_to_add = generator.resolve_modified_names(str(tmp_path), pr_files)
    assert set(modified_names) == {"my_indicator"}
    assert set(names_to_add) == {"my_indicator"}

def test_resolve_modified_names_collection_change_reverse_lookup(tmp_path):
    from generator import CatalogGenerator
    import json

    indicators_dir = tmp_path / "indicators"
    indicators_dir.mkdir()
    ind_file = indicators_dir / "parent_indicator.json"
    ind_data = {
        "Name": "parent_indicator",
        "Collections": ["sub_coll_a"]
    }
    with open(ind_file, 'w') as f:
        json.dump(ind_data, f)

    collections_dir = tmp_path / "collections"
    collections_dir.mkdir()
    coll_file = collections_dir / "sub_coll_a.json"
    coll_data = {"Name": "sub_coll_a"}
    with open(coll_file, 'w') as f:
        json.dump(coll_data, f)

    generator = CatalogGenerator(cache_dir=str(tmp_path / "cache"))
    pr_files = ["collections/sub_coll_a.json"]

    modified_names, names_to_add = generator.resolve_modified_names(str(tmp_path), pr_files)
    # sub_coll_a is part of parent_indicator and not in catalog config, so map to parent_indicator
    assert set(modified_names) == {"parent_indicator"}
    assert set(names_to_add) == {"parent_indicator"}

def test_resolve_modified_names_collection_change_explicit_in_catalog(tmp_path):
    from generator import CatalogGenerator
    import json

    catalogs_dir = tmp_path / "catalogs"
    catalogs_dir.mkdir()
    with open(catalogs_dir / "cat.json", 'w') as f:
        json.dump({"id": "cat", "collections": ["explicit_coll"]}, f)

    collections_dir = tmp_path / "collections"
    collections_dir.mkdir()
    with open(collections_dir / "explicit_coll.json", 'w') as f:
        json.dump({"Name": "explicit_coll"}, f)

    generator = CatalogGenerator(cache_dir=str(tmp_path / "cache"))
    pr_files = ["collections/explicit_coll.json"]

    modified_names, names_to_add = generator.resolve_modified_names(str(tmp_path), pr_files)
    assert set(modified_names) == {"explicit_coll"}
    assert set(names_to_add) == {"explicit_coll"}

def test_resolve_modified_names_catalog_change(tmp_path):
    from generator import CatalogGenerator
    import json

    catalogs_dir = tmp_path / "catalogs"
    catalogs_dir.mkdir()
    cat_file = catalogs_dir / "main_cat.json"
    cat_data = {
        "id": "main",
        "collections": ["coll_1", "coll_2"]
    }
    with open(cat_file, 'w') as f:
        json.dump(cat_data, f)

    generator = CatalogGenerator(cache_dir=str(tmp_path / "cache"))
    pr_files = ["catalogs/main_cat.json"]

    modified_names, names_to_add = generator.resolve_modified_names(str(tmp_path), pr_files)
    assert set(modified_names) == {"coll_1", "coll_2"}
    assert set(names_to_add) == {"coll_1", "coll_2"}

def test_check_eodash_catalog_errors(tmp_path):
    from generator import CatalogGenerator, CatalogGenerationError
    import json

    generator = CatalogGenerator(cache_dir=str(tmp_path / "cache"))
    
    # Case 1: Error in stderr logs
    stderr_with_error = "2026-11-25 [error] Error processing indicator my_ind: 'Type'"
    with pytest.raises(CatalogGenerationError) if pytest else pytest_raises(CatalogGenerationError):
        generator._check_eodash_catalog_errors(str(tmp_path), ["my_ind"], "", stderr_with_error)

    # Case 2: No catalog.json generated
    with pytest.raises(CatalogGenerationError) if pytest else pytest_raises(CatalogGenerationError):
        generator._check_eodash_catalog_errors(str(tmp_path / "non_existent"), ["my_ind"], "", "")

    # Case 3: Empty catalog with no child links when modified_names requested
    build_dir = tmp_path / "build" / "cat_id"
    build_dir.mkdir(parents=True)
    catalog_file = build_dir / "catalog.json"
    with open(catalog_file, "w") as f:
        json.dump({"type": "Catalog", "links": [{"rel": "root", "href": "./catalog.json"}]}, f)

    with pytest.raises(CatalogGenerationError) if pytest else pytest_raises(CatalogGenerationError):
        generator._check_eodash_catalog_errors(str(tmp_path / "build"), ["my_ind"], "", "")

def pytest_raises(exception_cls):
    class ContextManager:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None or not issubclass(exc_type, exception_cls):
                raise AssertionError(f"Expected {exception_cls.__name__} but got {exc_type}")
            return True
    return ContextManager()


