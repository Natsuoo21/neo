"""Obsidian tool — Create and manage .md notes in Obsidian vault.

Supports WSL: Windows paths (``G:\\Meu Drive\\vault``) are converted to
``/mnt/g/Meu Drive/vault``.  If the drive letter is not mounted in WSL
(common with Google Drive virtual drives), file I/O falls back to
PowerShell interop so the file lands on the Windows filesystem.
"""

import logging
import os
import platform
import re
import subprocess
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Module-level vault override — set by the orchestrator from user profile
_vault_override: str | None = None


def set_vault_path(path: str | None) -> None:
    """Set the vault path from user profile (called by orchestrator)."""
    global _vault_override
    _vault_override = path


def _convert_windows_path(path: str) -> str:
    """Convert a Windows path to WSL/Linux path if running under WSL.

    Examples:
        ``G:\\Meu Drive\\notes`` → ``/mnt/g/Meu Drive/notes``
        ``C:\\Users\\andre\\vault`` → ``/mnt/c/Users/andre/vault``

    If not a Windows-style path or not on WSL, returns unchanged.
    """
    if not path:
        return path

    # Detect Windows drive letter pattern: X:\ or X:/
    match = re.match(r"^([A-Za-z]):[/\\](.*)$", path)
    if not match:
        return path

    # Only convert if we're on Linux (WSL)
    if platform.system() != "Linux":
        return path

    drive = match.group(1).lower()
    rest = match.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def _wsl_to_windows(path: str) -> str:
    """Convert ``/mnt/g/Foo/Bar`` back to ``G:\\Foo\\Bar`` for PowerShell.

    Returns *path* unchanged if it does not match ``/mnt/<letter>/…``.
    """
    match = re.match(r"^/mnt/([a-z])/(.*)$", path)
    if not match:
        return path
    drive = match.group(1).upper()
    rest = match.group(2).replace("/", "\\")
    return f"{drive}:\\{rest}"


def _needs_windows_io(path: str) -> bool:
    """Return True when *path* is on a WSL ``/mnt/<letter>/`` mount that
    does not actually exist (e.g. Google Drive virtual drive ``G:``).
    """
    match = re.match(r"^/mnt/([a-z])/", path)
    if not match:
        return False
    mount_point = f"/mnt/{match.group(1)}"
    return not os.path.isdir(mount_point)


def _write_file(path: str, content: str) -> None:
    """Write *content* to *path*, using PowerShell when the drive is not
    mounted in WSL (e.g. Google Drive ``G:``).
    """
    if _needs_windows_io(path):
        win_path = _wsl_to_windows(path)
        win_dir = _wsl_to_windows(os.path.dirname(path))
        # Escape single quotes for PowerShell string literals
        esc_dir = win_dir.replace("'", "''")
        esc_path = win_path.replace("'", "''")
        script = (
            f"$null = New-Item -ItemType Directory -Force -Path '{esc_dir}';"
            f"$c = [Console]::In.ReadToEnd();"
            f"[System.IO.File]::WriteAllText('{esc_path}', $c, "
            f"[System.Text.Encoding]::UTF8)"
        )
        logger.info("Writing via PowerShell to %s", win_path)
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            input=content,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise OSError(
                f"PowerShell write failed ({win_path}): {result.stderr.strip()}"
            )
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def _append_file(path: str, content: str) -> None:
    """Append *content* to *path*, using PowerShell when needed."""
    if _needs_windows_io(path):
        win_path = _wsl_to_windows(path)
        esc_path = win_path.replace("'", "''")
        script = (
            f"$c = [Console]::In.ReadToEnd();"
            f"[System.IO.File]::AppendAllText('{esc_path}', $c, "
            f"[System.Text.Encoding]::UTF8)"
        )
        logger.info("Appending via PowerShell to %s", win_path)
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            input=f"\n{content}\n",
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise OSError(
                f"PowerShell append failed ({win_path}): {result.stderr.strip()}"
            )
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n{content}\n")


def _get_default_vault() -> str:
    """Return the vault path, checking multiple sources.

    Priority:
    1. Module-level override (set from user profile by orchestrator)
    2. OBSIDIAN_VAULT_PATH environment variable
    3. Default ~/Documents/Neo/vault
    """
    # 1. Module override from user profile
    if _vault_override:
        converted = _convert_windows_path(_vault_override)
        return os.path.expanduser(converted)

    # 2. Environment variable
    env_path = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if env_path:
        converted = _convert_windows_path(env_path)
        return os.path.expanduser(converted)

    # 3. Default
    return os.path.expanduser("~/Documents/Neo/vault")


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
    _write_file(file_path, full_content)

    return file_path


def append_to_note(path: str, content: str) -> str:
    """Append content to an existing note.

    Only allows appending to files within the vault directory.
    Returns the file path.
    """
    _validate_vault_path(path)
    _append_file(path, content)
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
    # When using Windows IO the path may not exist on disk yet,
    # so we normalise instead of calling realpath (which would fail).
    if _needs_windows_io(path):
        norm_path = os.path.normpath(path)
        norm_vault = os.path.normpath(vault)
    else:
        norm_path = os.path.realpath(path)
        norm_vault = os.path.realpath(vault)
    if not norm_path.startswith(norm_vault + os.sep) and norm_path != norm_vault:
        raise ValueError(f"Path is outside the vault directory: {path}")
