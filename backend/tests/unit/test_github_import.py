"""Tests for GitHub skill import — URL parsing, download, validation."""

import os
from unittest.mock import MagicMock, patch

import pytest

from neo.skills.github_import import (
    download_and_validate,
    import_directory,
    import_from_github,
    import_single_file,
    to_raw_url,
)


# ============================================
# URL CONVERSION
# ============================================


class TestToRawUrl:
    def test_blob_url(self):
        url = "https://github.com/user/repo/blob/main/skills/email.md"
        raw = to_raw_url(url)
        assert raw == "https://raw.githubusercontent.com/user/repo/main/skills/email.md"

    def test_already_raw(self):
        url = "https://raw.githubusercontent.com/user/repo/main/skill.md"
        raw = to_raw_url(url)
        assert raw == url

    def test_invalid_url(self):
        url = "https://example.com/not-github"
        raw = to_raw_url(url)
        assert raw is None

    def test_tree_url_returns_none(self):
        """Tree (directory) URLs are not single-file URLs."""
        url = "https://github.com/user/repo/tree/main/skills/"
        raw = to_raw_url(url)
        assert raw is None

    def test_blob_url_with_branch(self):
        url = "https://github.com/anthropics/prompts/blob/v2/skills/writer.md"
        raw = to_raw_url(url)
        assert raw == "https://raw.githubusercontent.com/anthropics/prompts/v2/skills/writer.md"


# ============================================
# DOWNLOAD AND VALIDATE
# ============================================


class TestDownloadAndValidate:
    def test_valid_skill(self):
        skill_content = (
            "---\n"
            "name: remote_skill\n"
            "description: A remote skill\n"
            "task_types: [remote, test]\n"
            "tools: []\n"
            "---\n"
            "\n"
            "# Remote Skill\n"
            "Instructions for remote skill.\n"
        )

        mock_resp = MagicMock()
        mock_resp.text = skill_content
        mock_resp.raise_for_status = MagicMock()

        with patch("neo.skills.github_import.httpx.get", return_value=mock_resp):
            parsed = download_and_validate("https://raw.githubusercontent.com/user/repo/main/skill.md")

        assert parsed["name"] == "remote_skill"
        assert parsed["description"] == "A remote skill"
        assert "Remote Skill" in parsed["content"]

    def test_invalid_frontmatter_rejected(self):
        """Files without valid frontmatter are rejected."""
        mock_resp = MagicMock()
        mock_resp.text = "Just plain text, no frontmatter."
        mock_resp.raise_for_status = MagicMock()

        with patch("neo.skills.github_import.httpx.get", return_value=mock_resp):
            parsed = download_and_validate("https://example.com/bad.md")

        assert parsed == {}

    def test_http_error_returns_empty(self):
        import httpx

        with patch("neo.skills.github_import.httpx.get", side_effect=httpx.HTTPError("404")):
            parsed = download_and_validate("https://example.com/missing.md")

        assert parsed == {}


# ============================================
# IMPORT SINGLE FILE
# ============================================


class TestImportSingleFile:
    def test_import_blob_url(self, memory_db, monkeypatch, tmp_dir):
        from neo.skills import github_import

        monkeypatch.setattr(github_import, "_COMMUNITY_SKILLS_DIR", tmp_dir)

        skill_content = (
            "---\n"
            "name: imported_skill\n"
            "description: An imported skill\n"
            "task_types: [import]\n"
            "tools: []\n"
            "---\n"
            "\n"
            "# Imported\nDo things.\n"
        )

        mock_resp = MagicMock()
        mock_resp.text = skill_content
        mock_resp.raise_for_status = MagicMock()

        with patch("neo.skills.github_import.httpx.get", return_value=mock_resp):
            result = import_single_file(
                "https://github.com/user/repo/blob/main/skill.md",
                memory_db,
            )

        assert result is not None
        assert result["name"] == "imported_skill"

        # File should exist in community dir
        expected = os.path.join(tmp_dir, "imported_skill.md")
        assert os.path.isfile(expected)

        # DB entry should exist
        row = memory_db.execute(
            "SELECT * FROM skills WHERE name = ?", ("imported_skill",)
        ).fetchone()
        assert row is not None
        assert row["skill_type"] == "community"

    def test_import_invalid_url_returns_none(self, memory_db):
        result = import_single_file("https://example.com/not-github", memory_db)
        assert result is None


# ============================================
# IMPORT DIRECTORY
# ============================================


class TestImportDirectory:
    def test_import_directory(self, memory_db, monkeypatch, tmp_dir):
        from neo.skills import github_import

        monkeypatch.setattr(github_import, "_COMMUNITY_SKILLS_DIR", tmp_dir)

        # Mock GitHub API directory listing
        api_response = MagicMock()
        api_response.json.return_value = [
            {
                "type": "file",
                "name": "writer.md",
                "download_url": "https://raw.githubusercontent.com/user/repo/main/skills/writer.md",
            },
            {
                "type": "file",
                "name": "readme.txt",
                "download_url": "https://raw.githubusercontent.com/user/repo/main/skills/readme.txt",
            },
            {
                "type": "dir",
                "name": "subdir",
            },
        ]
        api_response.raise_for_status = MagicMock()

        # Mock file download
        skill_content = (
            "---\n"
            "name: dir_skill\n"
            "description: From directory\n"
            "task_types: [dir]\n"
            "tools: []\n"
            "---\n"
            "\n"
            "# Dir Skill\nInstructions.\n"
        )
        file_response = MagicMock()
        file_response.text = skill_content
        file_response.raise_for_status = MagicMock()

        def mock_get(url, **kwargs):
            if "api.github.com" in url:
                return api_response
            return file_response

        with patch("neo.skills.github_import.httpx.get", side_effect=mock_get):
            imported = import_directory(
                "https://github.com/user/repo/tree/main/skills",
                memory_db,
            )

        assert len(imported) == 1
        assert imported[0]["name"] == "dir_skill"

    def test_invalid_tree_url(self, memory_db):
        imported = import_directory("https://example.com/not-github", memory_db)
        assert imported == []


# ============================================
# SMART IMPORT
# ============================================


class TestImportFromGithub:
    def test_detects_tree_url(self, memory_db, monkeypatch, tmp_dir):
        """Tree URLs route to import_directory."""
        from neo.skills import github_import

        monkeypatch.setattr(github_import, "_COMMUNITY_SKILLS_DIR", tmp_dir)

        api_response = MagicMock()
        api_response.json.return_value = []
        api_response.raise_for_status = MagicMock()

        with patch("neo.skills.github_import.httpx.get", return_value=api_response):
            result = import_from_github(
                "https://github.com/user/repo/tree/main/skills",
                memory_db,
            )

        assert result == []

    def test_detects_blob_url(self, memory_db, monkeypatch, tmp_dir):
        """Blob URLs route to import_single_file."""
        from neo.skills import github_import

        monkeypatch.setattr(github_import, "_COMMUNITY_SKILLS_DIR", tmp_dir)

        skill_content = (
            "---\nname: smart_import\ndescription: test\ntask_types: []\ntools: []\n---\n\nContent.\n"
        )
        mock_resp = MagicMock()
        mock_resp.text = skill_content
        mock_resp.raise_for_status = MagicMock()

        with patch("neo.skills.github_import.httpx.get", return_value=mock_resp):
            result = import_from_github(
                "https://github.com/user/repo/blob/main/skill.md",
                memory_db,
            )

        assert len(result) == 1
        assert result[0]["name"] == "smart_import"
