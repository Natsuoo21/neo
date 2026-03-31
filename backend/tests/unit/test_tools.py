"""Tests for all tool modules — Excel, PowerPoint, Word, Obsidian, Files."""

import os
import tempfile

import pytest
from openpyxl import load_workbook
from pptx import Presentation

from neo.tools.excel import create_workbook
from neo.tools.files import manage_file
from neo.tools.obsidian import append_to_note, create_note
from neo.tools.powerpoint import create_presentation
from neo.tools.word import create_document


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


# ============================================
# EXCEL
# ============================================


class TestExcel:
    def test_create_empty_workbook(self, tmp_dir):
        path = create_workbook(title=os.path.join(tmp_dir, "Test"))
        assert os.path.exists(path)
        assert path.endswith(".xlsx")

    def test_create_with_sheets_and_data(self, tmp_dir):
        sheets = [
            {
                "name": "Sales",
                "headers": ["Month", "Revenue", "Profit"],
                "rows": [
                    ["January", 10000, 3000],
                    ["February", 12000, 4000],
                ],
            },
            {
                "name": "Summary",
                "headers": ["Metric", "Value"],
                "rows": [["Total Revenue", 22000]],
            },
        ]
        path = create_workbook(title=os.path.join(tmp_dir, "Report"), sheets=sheets)
        assert os.path.exists(path)

        # Verify structure
        wb = load_workbook(path)
        assert len(wb.sheetnames) == 2
        assert "Sales" in wb.sheetnames
        assert "Summary" in wb.sheetnames

        ws = wb["Sales"]
        assert ws.cell(1, 1).value == "Month"
        assert ws.cell(1, 2).value == "Revenue"
        assert ws.cell(2, 1).value == "January"
        assert ws.cell(2, 2).value == 10000
        assert ws.cell(3, 2).value == 12000
        wb.close()

    def test_headers_are_styled(self, tmp_dir):
        sheets = [{"name": "Data", "headers": ["A", "B"], "rows": []}]
        path = create_workbook(title=os.path.join(tmp_dir, "Styled"), sheets=sheets)
        wb = load_workbook(path)
        ws = wb["Data"]
        cell = ws.cell(1, 1)
        assert cell.font.bold is True
        wb.close()

    def test_freeze_panes_on_header(self, tmp_dir):
        sheets = [{"name": "Data", "headers": ["A"], "rows": []}]
        path = create_workbook(title=os.path.join(tmp_dir, "Freeze"), sheets=sheets)
        wb = load_workbook(path)
        ws = wb["Data"]
        assert ws.freeze_panes == "A2"
        wb.close()


# ============================================
# POWERPOINT
# ============================================


class TestPowerPoint:
    def test_create_empty_presentation(self, tmp_dir):
        path = create_presentation(title=os.path.join(tmp_dir, "Deck"))
        assert os.path.exists(path)
        assert path.endswith(".pptx")

    def test_create_with_slides(self, tmp_dir):
        slides = [
            {"title": "Welcome", "content": "Introduction to the project"},
            {"title": "Overview", "content": "Key metrics and findings"},
            {"title": "Conclusion", "content": "Next steps"},
        ]
        path = create_presentation(title=os.path.join(tmp_dir, "Report"), slides=slides)
        assert os.path.exists(path)

        prs = Presentation(path)
        assert len(prs.slides) == 3
        assert prs.slides[0].shapes.title.text == "Welcome"

    def test_single_slide_has_title(self, tmp_dir):
        path = create_presentation(title=os.path.join(tmp_dir, "Single"))
        prs = Presentation(path)
        assert len(prs.slides) == 1
        assert prs.slides[0].shapes.title.text == "Single"


# ============================================
# WORD
# ============================================


class TestWord:
    def test_create_empty_document(self, tmp_dir):
        path = create_document(title=os.path.join(tmp_dir, "Doc"))
        assert os.path.exists(path)
        assert path.endswith(".docx")

    def test_create_with_content(self, tmp_dir):
        content = "# Introduction\nThis is the first section.\n## Details\n- Item one\n- Item two"
        path = create_document(title=os.path.join(tmp_dir, "Report"), content=content)
        assert os.path.exists(path)

        from docx import Document

        doc = Document(path)
        # Title + headings + paragraphs + list items
        assert len(doc.paragraphs) >= 4

    def test_headings_converted(self, tmp_dir):
        content = "# Heading 1\n## Heading 2\n### Heading 3"
        path = create_document(title=os.path.join(tmp_dir, "Headings"), content=content)

        from docx import Document

        doc = Document(path)
        heading_styles = [p.style.name for p in doc.paragraphs if "Heading" in p.style.name]
        assert len(heading_styles) >= 3


# ============================================
# OBSIDIAN
# ============================================


class TestObsidian:
    def test_create_note_basic(self, tmp_dir, monkeypatch):
        monkeypatch.setattr("neo.tools.obsidian._get_default_vault", lambda: tmp_dir)
        path = create_note(title="Test Note", content="Hello world")
        assert os.path.exists(path)
        assert path.endswith(".md")

        with open(path) as f:
            text = f.read()
        assert "---" in text  # frontmatter
        assert "title: Test Note" in text
        assert "# Test Note" in text
        assert "Hello world" in text

    def test_create_note_with_tags(self, tmp_dir, monkeypatch):
        monkeypatch.setattr("neo.tools.obsidian._get_default_vault", lambda: tmp_dir)
        path = create_note(title="Tagged", tags=["project", "neo"])

        with open(path) as f:
            text = f.read()
        assert "tags: [project, neo]" in text

    def test_create_note_with_backlinks(self, tmp_dir, monkeypatch):
        monkeypatch.setattr("neo.tools.obsidian._get_default_vault", lambda: tmp_dir)
        path = create_note(title="Linked", links=["Other Note", "Reference"])

        with open(path) as f:
            text = f.read()
        assert "[[Other Note]]" in text
        assert "[[Reference]]" in text

    def test_frontmatter_has_date(self, tmp_dir, monkeypatch):
        monkeypatch.setattr("neo.tools.obsidian._get_default_vault", lambda: tmp_dir)
        path = create_note(title="Dated")

        with open(path) as f:
            text = f.read()
        assert "date:" in text
        assert "created_by: neo" in text

    def test_append_to_note(self, tmp_dir, monkeypatch):
        monkeypatch.setattr("neo.tools.obsidian._get_default_vault", lambda: tmp_dir)
        path = create_note(title="Append Test", content="Initial")
        append_to_note(path, "Added later")

        with open(path) as f:
            text = f.read()
        assert "Initial" in text
        assert "Added later" in text


# ============================================
# FILE SYSTEM
# ============================================


class TestFiles:
    def test_move_file(self, tmp_dir):
        src = os.path.join(tmp_dir, "source.txt")
        dst = os.path.join(tmp_dir, "dest.txt")
        with open(src, "w") as f:
            f.write("content")

        result = manage_file("move", src, dst)
        assert "Moved" in result
        assert not os.path.exists(src)
        assert os.path.exists(dst)

    def test_copy_file(self, tmp_dir):
        src = os.path.join(tmp_dir, "source.txt")
        dst = os.path.join(tmp_dir, "copy.txt")
        with open(src, "w") as f:
            f.write("content")

        result = manage_file("copy", src, dst)
        assert "Copied" in result
        assert os.path.exists(src)  # original still there
        assert os.path.exists(dst)

    def test_rename_file(self, tmp_dir):
        src = os.path.join(tmp_dir, "old.txt")
        with open(src, "w") as f:
            f.write("content")

        result = manage_file("rename", src, os.path.join(tmp_dir, "new.txt"))
        assert "Renamed" in result
        assert not os.path.exists(src)
        assert os.path.exists(os.path.join(tmp_dir, "new.txt"))

    def test_delete_file(self, tmp_dir):
        src = os.path.join(tmp_dir, "to_delete.txt")
        with open(src, "w") as f:
            f.write("content")

        result = manage_file("delete", src)
        assert "Deleted" in result
        assert not os.path.exists(src)

    def test_source_not_found(self):
        result = manage_file("move", "/nonexistent/file.txt", "/tmp/dst.txt")
        assert "Error" in result

    def test_delete_directory_refused(self, tmp_dir):
        result = manage_file("delete", tmp_dir)
        assert "Error" in result
        assert "refusing" in result.lower()

    def test_unknown_action(self, tmp_dir):
        src = os.path.join(tmp_dir, "file.txt")
        with open(src, "w") as f:
            f.write("x")
        result = manage_file("explode", src)
        assert "Error" in result

    def test_safety_check_system_dir(self):
        with pytest.raises(ValueError, match="protected"):
            manage_file("delete", "/bin/bash")
