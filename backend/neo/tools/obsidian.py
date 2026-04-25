"""Obsidian tool — Create, read, search and manage .md notes in Obsidian vault.

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
from difflib import SequenceMatcher

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
            raise OSError(f"PowerShell write failed ({win_path}): {result.stderr.strip()}")
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
            raise OSError(f"PowerShell append failed ({win_path}): {result.stderr.strip()}")
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n{content}\n")


def _read_file(path: str) -> str:
    """Read file content, using PowerShell when the drive is not mounted."""
    if _needs_windows_io(path):
        win_path = _wsl_to_windows(path)
        esc_path = win_path.replace("'", "''")
        script = f"[System.IO.File]::ReadAllText('{esc_path}', [System.Text.Encoding]::UTF8)"
        logger.info("Reading via PowerShell from %s", win_path)
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise OSError(f"PowerShell read failed ({win_path}): {result.stderr.strip()}")
        return result.stdout
    else:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()


_SKIP_DIRS = {".obsidian", "node_modules", ".git", ".trash", ".DS_Store"}


def _list_files(directory: str) -> list[str]:
    """List all .md files recursively, skipping hidden/system directories."""
    if _needs_windows_io(directory):
        win_dir = _wsl_to_windows(directory)
        esc_dir = win_dir.replace("'", "''")
        # Exclude .obsidian and node_modules via PowerShell Where-Object
        script = (
            f"Get-ChildItem -Path '{esc_dir}' -Filter '*.md' -Recurse -File "
            f"| Where-Object {{ $_.FullName -notmatch '[\\\\/](\\.obsidian|node_modules|\\."
            f"git|\\..trash)[\\\\/]' }} "
            f"| ForEach-Object {{ $_.FullName }}"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return []
        paths = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line:
                paths.append(_convert_windows_path(line))
        return paths
    else:
        paths = []
        for root, dirs, files in os.walk(directory):
            # Prune directories we should skip
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fname in files:
                if fname.lower().endswith(".md"):
                    paths.append(os.path.join(root, fname))
        return paths


def _fuzzy_match(query: str, candidate: str) -> float:
    """Return a similarity score (0-1) between query and candidate."""
    q = query.lower().strip()
    c = candidate.lower().strip()
    # Exact match
    if q == c:
        return 1.0
    # Substring match gets a high score
    if q in c:
        return 0.85 + (len(q) / len(c)) * 0.1
    if c in q:
        return 0.8
    # Sequence matcher for fuzzy similarity
    return SequenceMatcher(None, q, c).ratio()


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


# ---------------------------------------------------------------------------
#  READ / SEARCH / LIST
# ---------------------------------------------------------------------------


def read_note(name: str) -> str:
    """Read an Obsidian note by name, with fuzzy matching.

    The *name* can be:
    - An exact filename (``My Note.md``)
    - A note title without extension (``My Note``)
    - A partial/approximate name (``my note``, ``mynote``)
    - A subfolder path (``projects/My Note``)

    Uses fuzzy matching to find the best candidate when no exact match exists.

    Returns a JSON string with the note path, title, and content.
    """
    import json as _json

    vault = _get_default_vault()
    all_files = _list_files(vault)

    if not all_files:
        return _json.dumps({"error": "No notes found in vault", "vault": vault})

    query = name.strip()

    # Build candidates: (path, relative_path, stem)
    candidates = []
    for fpath in all_files:
        rel = os.path.relpath(fpath, vault)
        stem = os.path.splitext(os.path.basename(fpath))[0]
        candidates.append((fpath, rel, stem))

    # 1. Try exact filename match (with or without .md)
    query_md = query if query.lower().endswith(".md") else query + ".md"
    for fpath, rel, stem in candidates:
        if rel == query_md or rel == query or os.path.basename(fpath) == query_md:
            content = _read_file(fpath)
            return _json.dumps({
                "path": fpath,
                "relative_path": rel,
                "title": stem,
                "content": content,
            })

    # 2. Try case-insensitive exact match
    q_lower = query.lower().replace(".md", "")
    for fpath, rel, stem in candidates:
        if stem.lower() == q_lower:
            content = _read_file(fpath)
            return _json.dumps({
                "path": fpath,
                "relative_path": rel,
                "title": stem,
                "content": content,
            })

    # 3. Fuzzy match — score all candidates, return best match
    scored = []
    for fpath, rel, stem in candidates:
        # Score against stem (filename without extension)
        score_stem = _fuzzy_match(query, stem)
        # Also score against stem with spaces instead of underscores/hyphens
        stem_clean = stem.replace("_", " ").replace("-", " ")
        score_clean = _fuzzy_match(query, stem_clean)
        # Also score against relative path
        score_rel = _fuzzy_match(query, rel.replace(".md", ""))
        best_score = max(score_stem, score_clean, score_rel)
        scored.append((best_score, fpath, rel, stem))

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0]

    if best[0] < 0.3:
        # No good match — return top 5 suggestions
        suggestions = [s[3] for s in scored[:5]]
        return _json.dumps({
            "error": f"No note matching '{query}' found",
            "suggestions": suggestions,
            "vault": vault,
        })

    fpath, rel, stem = best[1], best[2], best[3]
    content = _read_file(fpath)

    result = {
        "path": fpath,
        "relative_path": rel,
        "title": stem,
        "content": content,
        "match_score": round(best[0], 2),
    }

    # If match is not perfect, also include alternatives
    if best[0] < 0.9 and len(scored) > 1:
        result["other_matches"] = [
            {"title": s[3], "score": round(s[0], 2)}
            for s in scored[1:4]
            if s[0] > 0.3
        ]

    return _json.dumps(result)


def search_notes(query: str, limit: int = 10) -> str:
    """Search notes in the vault by title and content.

    Searches both filenames and file contents for the query string.
    Returns matching notes with context snippets.
    """
    import json as _json

    vault = _get_default_vault()
    all_files = _list_files(vault)

    if not all_files:
        return _json.dumps({"results": [], "total": 0, "vault": vault})

    q_lower = query.lower()
    results = []

    for fpath in all_files:
        rel = os.path.relpath(fpath, vault)
        stem = os.path.splitext(os.path.basename(fpath))[0]

        # Score by title match
        title_score = 0
        stem_lower = stem.lower().replace("_", " ").replace("-", " ")
        if q_lower in stem_lower:
            title_score = 0.8
        elif _fuzzy_match(query, stem) > 0.5:
            title_score = _fuzzy_match(query, stem) * 0.6

        # Score by content match
        content_score = 0
        snippet = ""
        try:
            content = _read_file(fpath)
            content_lower = content.lower()
            if q_lower in content_lower:
                content_score = 0.6
                # Extract snippet around the match
                idx = content_lower.index(q_lower)
                start = max(0, idx - 80)
                end = min(len(content), idx + len(query) + 80)
                snippet = content[start:end].strip()
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."
        except Exception:
            pass

        total_score = max(title_score, content_score)
        if title_score > 0 and content_score > 0:
            total_score = title_score + content_score * 0.5

        if total_score > 0.1:
            results.append({
                "title": stem,
                "relative_path": rel,
                "score": round(total_score, 2),
                "snippet": snippet,
            })

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:limit]

    return _json.dumps({
        "query": query,
        "results": results,
        "total": len(results),
    })


def list_notes(folder: str = "", limit: int = 50) -> str:
    """List notes in the Obsidian vault.

    Args:
        folder: Optional subfolder to list (e.g. "projects", "daily").
                 Empty string lists from vault root.
        limit: Maximum number of notes to return.

    Returns a JSON string with the list of notes and their metadata.
    """
    import json as _json

    vault = _get_default_vault()
    search_dir = vault

    if folder:
        search_dir = os.path.join(vault, folder)
        # Validate still within vault
        _validate_vault_path(search_dir)

    all_files = _list_files(search_dir)

    notes = []
    for fpath in all_files:
        rel = os.path.relpath(fpath, vault)
        stem = os.path.splitext(os.path.basename(fpath))[0]

        # Get file size and modification time
        try:
            if _needs_windows_io(fpath):
                stat_info = None
            else:
                stat_info = os.stat(fpath)
        except OSError:
            stat_info = None

        note_info: dict = {
            "title": stem,
            "relative_path": rel,
        }
        if stat_info:
            note_info["size_bytes"] = stat_info.st_size
            note_info["modified"] = datetime.fromtimestamp(
                stat_info.st_mtime, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M")

        # Extract tags from frontmatter (quick parse)
        try:
            content = _read_file(fpath)
            if content.startswith("---"):
                fm_end = content.find("---", 3)
                if fm_end > 0:
                    fm = content[3:fm_end]
                    tag_match = re.search(r"tags:\s*\[([^\]]*)\]", fm)
                    if tag_match:
                        tags = [t.strip() for t in tag_match.group(1).split(",") if t.strip()]
                        if tags:
                            note_info["tags"] = tags
        except Exception:
            pass

        notes.append(note_info)

    # Sort by modification time (newest first) if available
    notes.sort(key=lambda n: n.get("modified", ""), reverse=True)
    notes = notes[:limit]

    # Collect folder structure
    folders = set()
    for fpath in all_files:
        rel = os.path.relpath(fpath, vault)
        parent = os.path.dirname(rel)
        if parent and parent != ".":
            folders.add(parent)

    return _json.dumps({
        "vault": vault,
        "folder_filter": folder or "(root)",
        "notes": notes,
        "total": len(notes),
        "folders": sorted(folders),
    })
