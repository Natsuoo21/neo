"""Word tool — Create and edit .docx files via python-docx."""

import os

from docx import Document

_DEFAULT_SAVE_DIR = os.path.expanduser(os.environ.get("DEFAULT_SAVE_DIR", "~/Documents/Neo"))


def create_document(title: str, content: str = "", style: str = "Normal") -> str:
    """Create a new Word document.

    Args:
        title: Filename (without extension) or full path.
        content: Document body. Lines starting with # are converted to headings.
        style: Default paragraph style.

    Returns:
        Absolute path to the created .docx file.
    """
    doc = Document()

    # Add title as Heading 1
    doc.add_heading(title, level=0)

    if content:
        for line in content.split("\n"):
            line = line.rstrip()
            if not line:
                doc.add_paragraph("")
            elif line.startswith("### "):
                doc.add_heading(line[4:], level=3)
            elif line.startswith("## "):
                doc.add_heading(line[3:], level=2)
            elif line.startswith("# "):
                doc.add_heading(line[2:], level=1)
            elif line.startswith("- "):
                doc.add_paragraph(line[2:], style="List Bullet")
            else:
                doc.add_paragraph(line, style=style)

    file_path = _resolve_path(title, ".docx")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    doc.save(file_path)
    return file_path


def _resolve_path(title: str, extension: str) -> str:
    """Resolve a title to an absolute file path."""
    if os.path.isabs(title):
        if not title.endswith(extension):
            title += extension
        return title

    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    safe_name = safe_name.strip().replace(" ", "_")
    if not safe_name.endswith(extension):
        safe_name += extension

    save_dir = os.path.expanduser(_DEFAULT_SAVE_DIR)
    return os.path.join(save_dir, safe_name)
