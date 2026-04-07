"""Tests for the Skills system — loader, parser, routing, slash commands."""

import os
import tempfile

import pytest

from neo.skills.loader import (
    _parse_simple_yaml,
    create_user_skill,
    delete_skill,
    get_available_skill_commands,
    get_skill_by_name,
    load_all_skills,
    parse_skill_file,
    parse_slash_command,
    resolve_skill_slug,
    route_skill,
    sync_skills_to_db,
    toggle_skill,
)


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_skill_file(tmp_dir):
    """Create a valid skill file and return its path."""
    path = os.path.join(tmp_dir, "test_skill.md")
    with open(path, "w") as f:
        f.write(
            "---\n"
            "name: test_skill\n"
            "description: A test skill\n"
            "task_types: [test, demo, example]\n"
            "tools: [create_excel]\n"
            "---\n"
            "\n"
            "# Test Skill\n"
            "\n"
            "These are the instructions for the LLM.\n"
        )
    return path


# ============================================
# YAML PARSER
# ============================================


class TestYamlParser:
    def test_parse_simple_key_value(self):
        raw = "name: my_skill\ndescription: Does things"
        result = _parse_simple_yaml(raw)
        assert result["name"] == "my_skill"
        assert result["description"] == "Does things"

    def test_parse_inline_list(self):
        raw = "task_types: [email, write, draft]"
        result = _parse_simple_yaml(raw)
        assert result["task_types"] == ["email", "write", "draft"]

    def test_parse_empty_list(self):
        raw = "tools: []"
        result = _parse_simple_yaml(raw)
        assert result["tools"] == []

    def test_parse_ignores_comments(self):
        raw = "# comment\nname: test"
        result = _parse_simple_yaml(raw)
        assert result["name"] == "test"
        assert "#" not in result

    def test_parse_strips_quotes(self):
        raw = 'name: "quoted_name"'
        result = _parse_simple_yaml(raw)
        assert result["name"] == "quoted_name"


# ============================================
# SKILL FILE PARSING
# ============================================


class TestParseSkillFile:
    def test_parse_valid_skill(self, sample_skill_file):
        skill = parse_skill_file(sample_skill_file)
        assert skill["name"] == "test_skill"
        assert skill["description"] == "A test skill"
        assert skill["task_types"] == ["test", "demo", "example"]
        assert skill["tools"] == ["create_excel"]
        assert "Test Skill" in skill["content"]
        assert "instructions for the LLM" in skill["content"]

    def test_parse_returns_file_path(self, sample_skill_file):
        skill = parse_skill_file(sample_skill_file)
        assert skill["file_path"] == sample_skill_file

    def test_parse_missing_frontmatter(self, tmp_dir):
        path = os.path.join(tmp_dir, "no_front.md")
        with open(path, "w") as f:
            f.write("Just plain content, no frontmatter.")
        result = parse_skill_file(path)
        assert result == {}

    def test_parse_missing_name(self, tmp_dir):
        path = os.path.join(tmp_dir, "no_name.md")
        with open(path, "w") as f:
            f.write("---\ndescription: Missing name\n---\nContent here.")
        result = parse_skill_file(path)
        assert result == {}

    def test_parse_nonexistent_file(self):
        result = parse_skill_file("/nonexistent/skill.md")
        assert result == {}

    def test_parse_malformed_frontmatter(self, tmp_dir):
        path = os.path.join(tmp_dir, "bad.md")
        with open(path, "w") as f:
            f.write("---\nname: test\nNo closing delimiter")
        result = parse_skill_file(path)
        assert result == {}


# ============================================
# LOAD ALL SKILLS
# ============================================


class TestLoadAllSkills:
    def test_loads_public_skills(self, monkeypatch):
        """Verify built-in public skills are loadable."""
        skills = load_all_skills()
        names = [s["name"] for s in skills]
        assert "email_writer" in names
        assert "spreadsheet_builder" in names
        assert "meeting_notes" in names

    def test_loads_from_custom_dir(self, tmp_dir, monkeypatch):
        """Skills from custom dir are loaded."""
        monkeypatch.setattr("neo.skills.loader._SKILLS_DIR", tmp_dir)
        monkeypatch.setattr("neo.skills.loader._USER_SKILLS_DIR", "/nonexistent")
        monkeypatch.setattr("neo.skills.loader._COMMUNITY_SKILLS_DIR", "/nonexistent2")

        # Create a skill in tmp_dir
        with open(os.path.join(tmp_dir, "custom.md"), "w") as f:
            f.write("---\nname: custom_skill\ntask_types: [custom]\n---\nCustom instructions.")

        skills = load_all_skills()
        assert len(skills) == 1
        assert skills[0]["name"] == "custom_skill"

    def test_ignores_non_md_files(self, tmp_dir, monkeypatch):
        monkeypatch.setattr("neo.skills.loader._SKILLS_DIR", tmp_dir)
        monkeypatch.setattr("neo.skills.loader._USER_SKILLS_DIR", "/nonexistent")
        monkeypatch.setattr("neo.skills.loader._COMMUNITY_SKILLS_DIR", "/nonexistent2")

        with open(os.path.join(tmp_dir, "readme.txt"), "w") as f:
            f.write("Not a skill file")
        with open(os.path.join(tmp_dir, ".gitkeep"), "w") as f:
            f.write("")

        skills = load_all_skills()
        assert len(skills) == 0


# ============================================
# SYNC TO DATABASE
# ============================================


class TestSyncSkillsToDb:
    def test_sync_inserts_skills(self, memory_db):
        count = sync_skills_to_db(memory_db)
        assert count >= 3  # At least the 3 built-in skills

    def test_sync_is_idempotent(self, memory_db):
        count1 = sync_skills_to_db(memory_db)
        count2 = sync_skills_to_db(memory_db)
        assert count1 == count2


# ============================================
# SKILL ROUTING (legacy keyword-based)
# ============================================


class TestRouteSkill:
    def test_routes_email_command(self, memory_db):
        sync_skills_to_db(memory_db)
        content = route_skill("write an email to John", memory_db)
        assert "Email Writer" in content or "email" in content.lower()

    def test_routes_spreadsheet_command(self, memory_db):
        sync_skills_to_db(memory_db)
        content = route_skill("create an excel spreadsheet for the budget", memory_db)
        assert "Spreadsheet" in content or "spreadsheet" in content.lower()

    def test_routes_meeting_command(self, memory_db):
        sync_skills_to_db(memory_db)
        content = route_skill("take meeting notes for today's standup", memory_db)
        assert "Meeting" in content or "meeting" in content.lower()

    def test_no_match_returns_empty(self, memory_db):
        sync_skills_to_db(memory_db)
        content = route_skill("what time is it", memory_db)
        assert content == ""

    def test_routes_without_synced_skills(self, memory_db):
        """No skills synced — should return empty."""
        content = route_skill("write an email", memory_db)
        assert content == ""


# ============================================
# SLASH COMMAND PARSING
# ============================================


class TestParseSlashCommand:
    def test_valid_slash_command(self):
        slug, remainder = parse_slash_command("/email write a follow-up")
        assert slug == "email"
        assert remainder == "write a follow-up"

    def test_slash_no_remainder(self):
        slug, remainder = parse_slash_command("/email")
        assert slug == "email"
        assert remainder == ""

    def test_normal_command_no_slash(self):
        slug, remainder = parse_slash_command("write an email")
        assert slug == ""
        assert remainder == "write an email"

    def test_whitespace_handling(self):
        slug, remainder = parse_slash_command("  /meeting   take notes  ")
        assert slug == "meeting"
        assert remainder == "take notes"

    def test_empty_slash(self):
        slug, remainder = parse_slash_command("/")
        assert slug == ""
        assert remainder == "/"

    def test_empty_string(self):
        slug, remainder = parse_slash_command("")
        assert slug == ""
        assert remainder == ""


# ============================================
# RESOLVE SKILL SLUG
# ============================================


class TestResolveSkillSlug:
    def test_exact_match(self, memory_db):
        sync_skills_to_db(memory_db)
        result = resolve_skill_slug("email_writer", memory_db)
        assert result == "email_writer"

    def test_prefix_match(self, memory_db):
        sync_skills_to_db(memory_db)
        result = resolve_skill_slug("email", memory_db)
        assert result == "email_writer"

    def test_no_match(self, memory_db):
        sync_skills_to_db(memory_db)
        result = resolve_skill_slug("nonexistent", memory_db)
        assert result is None

    def test_prefix_match_meeting(self, memory_db):
        sync_skills_to_db(memory_db)
        result = resolve_skill_slug("meeting", memory_db)
        assert result == "meeting_notes"


# ============================================
# GET SKILL BY NAME
# ============================================


class TestGetSkillByName:
    def test_valid_skill(self, memory_db):
        sync_skills_to_db(memory_db)
        name, content = get_skill_by_name("email_writer", memory_db)
        assert name == "email_writer"
        assert "Email Writer" in content

    def test_missing_skill(self, memory_db):
        sync_skills_to_db(memory_db)
        name, content = get_skill_by_name("nonexistent", memory_db)
        assert name == ""
        assert content == ""

    def test_disabled_skill(self, memory_db):
        sync_skills_to_db(memory_db)
        toggle_skill(memory_db, "email_writer", enabled=False)
        name, content = get_skill_by_name("email_writer", memory_db)
        assert name == ""
        assert content == ""


# ============================================
# GET AVAILABLE SKILL COMMANDS
# ============================================


class TestGetAvailableSkillCommands:
    def test_returns_all_enabled(self, memory_db):
        sync_skills_to_db(memory_db)
        commands = get_available_skill_commands(memory_db)
        names = [c["name"] for c in commands]
        assert "email_writer" in names
        assert all("description" in c for c in commands)

    def test_excludes_disabled(self, memory_db):
        sync_skills_to_db(memory_db)
        toggle_skill(memory_db, "email_writer", enabled=False)
        commands = get_available_skill_commands(memory_db)
        names = [c["name"] for c in commands]
        assert "email_writer" not in names


# ============================================
# DELETE SKILL
# ============================================


class TestDeleteSkill:
    def test_delete_user_skill(self, memory_db, tmp_dir):
        # Create a user skill first
        path = create_user_skill(
            memory_db,
            name="temp_skill",
            description="Temporary",
            task_types=["temp"],
            content="Temp instructions",
        )
        assert os.path.isfile(path)

        deleted = delete_skill(memory_db, "temp_skill")
        assert deleted is True
        assert not os.path.isfile(path)

        # Verify DB row is gone
        row = memory_db.execute(
            "SELECT * FROM skills WHERE name = ?", ("temp_skill",)
        ).fetchone()
        assert row is None

    def test_refuse_delete_public_skill(self, memory_db):
        sync_skills_to_db(memory_db)
        deleted = delete_skill(memory_db, "email_writer")
        assert deleted is False

        # Verify still exists
        row = memory_db.execute(
            "SELECT * FROM skills WHERE name = ?", ("email_writer",)
        ).fetchone()
        assert row is not None

    def test_delete_nonexistent(self, memory_db):
        deleted = delete_skill(memory_db, "nonexistent")
        assert deleted is False


# ============================================
# CREATE SKILL FROM TOOL
# ============================================


class TestCreateSkillFromTool:
    def test_creates_file_and_db_entry(self, memory_db, monkeypatch, tmp_dir):
        """LLM tool wrapper creates file + DB entry."""
        from neo.skills import loader

        monkeypatch.setattr(loader, "_USER_SKILLS_DIR", tmp_dir)

        path = create_user_skill(
            memory_db,
            name="meeting_agenda",
            description="Create meeting agendas",
            task_types=["meeting", "agenda"],
            content="# Meeting Agenda\nHelp create structured meeting agendas.",
            tools=["create_document"],
        )

        assert os.path.isfile(path)
        assert path.endswith("meeting_agenda.md")

        # Verify DB entry
        row = memory_db.execute(
            "SELECT * FROM skills WHERE name = ?", ("meeting_agenda",)
        ).fetchone()
        assert row is not None
        assert row["skill_type"] == "user"

        # Verify file content
        parsed = parse_skill_file(path)
        assert parsed["name"] == "meeting_agenda"
        assert parsed["description"] == "Create meeting agendas"
        assert "Meeting Agenda" in parsed["content"]
