"""Obsidian tool — Create and manage .md notes in Obsidian vault."""

import os
from datetime import datetime, timezone


def _get_default_vault() -> str:
    """Return the default vault path, evaluated at call time."""
    return os.path.expanduser(os.environ.get("OBSIDIAN_VAULT_PATH", "~/Documents/Neo/vault"))


def create_note(
    title: str,
    content: str = "",
    tags: list[str] | None = None,
    links: list[str] | None = None,
) -> str:
    """Create an Obsidian note with YAML frontmatter.

    Args:
        title: Note title (becomes filename).
        content: Note body in markdown.
        tags: List of tags for frontmatter.
        links: List of note titles to backlink ([[link]]).

    Returns:
        Absolute path to the created .md file.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tags = tags or []

    # Build YAML frontmatter
    frontmatter_lines = [
        "---",
        f"title: {title}",
        f"date: {now}",
        f"tags: [{', '.join(tags)}]",
        "created_by: neo",
        "---",
        "",
    ]

    # Build body
    body_lines = [f"# {title}", ""]
    if content:
        body_lines.append(content)
        body_lines.append("")

    # Add backlinks section
    if links:
        body_lines.append("## Related")
        for link in links:
            body_lines.append(f"- [[{link}]]")
        body_lines.append("")

    full_content = "\n".join(frontmatter_lines + body_lines)

    file_path = _resolve_vault_path(title)
    _validate_vault_path(file_path)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    return file_path


def append_to_note(path: str, content: str) -> str:
    """Append content to an existing note.

    Only allows appending to files within the vault directory.
    Returns the file path.
    """
    _validate_vault_path(path)

    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{content}\n")
    return path


def _resolve_vault_path(title: str) -> str:
    """Resolve a note title to a path in the Obsidian vault."""
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    safe_name = safe_name.strip().replace(" ", "_")
    if not safe_name.endswith(".md"):
        safe_name += ".md"

    vault = _get_default_vault()
    return os.path.join(vault, safe_name)


def _validate_vault_path(path: str) -> None:
    """Ensure the path is within the vault directory.

    Raises ValueError if path is outside the vault.
    """
    vault = _get_default_vault()
    real_path = os.path.realpath(path)
    real_vault = os.path.realpath(vault)
    if not real_path.startswith(real_vault + os.sep) and real_path != real_vault:
        raise ValueError(f"Path is outside the vault directory: {path}")
