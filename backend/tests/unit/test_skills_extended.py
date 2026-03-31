"""Tests for new skills and skill management functions."""

from neo.skills.loader import (
    list_skills,
    load_all_skills,
    route_skill_with_name,
    sync_skills_to_db,
    toggle_skill,
)


class TestNewSkillsLoaded:
    def test_eight_total_skills(self):
        skills = load_all_skills()
        names = {s["name"] for s in skills}
        assert len(skills) == 8
        assert "email_writer" in names
        assert "meeting_notes" in names
        assert "spreadsheet_builder" in names
        assert "word_document" in names
        assert "file_organizer" in names
        assert "research_synthesis" in names
        assert "obsidian_note" in names
        assert "presentation_builder" in names

    def test_word_document_skill_has_correct_task_types(self):
        skills = load_all_skills()
        word = next(s for s in skills if s["name"] == "word_document")
        assert "document" in word["task_types"]
        assert "word" in word["task_types"]
        assert "docx" in word["task_types"]
        assert "report" in word["task_types"]

    def test_file_organizer_skill_has_correct_task_types(self):
        skills = load_all_skills()
        organizer = next(s for s in skills if s["name"] == "file_organizer")
        assert "organize" in organizer["task_types"]
        assert "sort" in organizer["task_types"]
        assert "clean" in organizer["task_types"]

    def test_research_synthesis_skill_has_correct_task_types(self):
        skills = load_all_skills()
        research = next(s for s in skills if s["name"] == "research_synthesis")
        assert "research" in research["task_types"]
        assert "summarize" in research["task_types"]
        assert "compare" in research["task_types"]


class TestSkillRouting:
    def test_word_skill_routes_correctly(self, memory_db):
        sync_skills_to_db(memory_db)
        memory_db.commit()
        name, content = route_skill_with_name("create a document for the team", memory_db)
        assert name == "word_document"
        assert "Word Document Skill" in content

    def test_research_skill_routes_correctly(self, memory_db):
        sync_skills_to_db(memory_db)
        memory_db.commit()
        name, content = route_skill_with_name("research competitors in the market", memory_db)
        assert name == "research_synthesis"
        assert "Research Synthesis Skill" in content

    def test_file_organizer_routes_correctly(self, memory_db):
        sync_skills_to_db(memory_db)
        memory_db.commit()
        name, content = route_skill_with_name("organize my downloads folder", memory_db)
        assert name == "file_organizer"
        assert "File Organizer Skill" in content


class TestToggleSkill:
    def test_disable_skill(self, memory_db):
        sync_skills_to_db(memory_db)
        memory_db.commit()

        # Disable email_writer
        result = toggle_skill(memory_db, "email_writer", enabled=False)
        memory_db.commit()
        assert result is True

        # Verify it's not in enabled list
        enabled = list_skills(memory_db)
        names = {s["name"] for s in enabled}
        assert "email_writer" not in names

    def test_reenable_skill(self, memory_db):
        sync_skills_to_db(memory_db)
        memory_db.commit()

        # Disable then re-enable
        toggle_skill(memory_db, "email_writer", enabled=False)
        memory_db.commit()
        toggle_skill(memory_db, "email_writer", enabled=True)
        memory_db.commit()

        enabled = list_skills(memory_db)
        names = {s["name"] for s in enabled}
        assert "email_writer" in names

    def test_toggle_nonexistent_skill(self, memory_db):
        result = toggle_skill(memory_db, "nonexistent_skill", enabled=False)
        assert result is False


class TestListSkills:
    def test_lists_all_enabled(self, memory_db):
        sync_skills_to_db(memory_db)
        memory_db.commit()
        skills = list_skills(memory_db)
        assert len(skills) == 8

    def test_disabled_not_listed(self, memory_db):
        sync_skills_to_db(memory_db)
        memory_db.commit()
        toggle_skill(memory_db, "email_writer", enabled=False)
        memory_db.commit()
        skills = list_skills(memory_db)
        assert len(skills) == 7
