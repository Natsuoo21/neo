"""File system tool — Move, rename, copy, delete, organize files."""

import os
import shutil

from neo.tools.paths import PROTECTED_DIRS, _validate_write_path


def manage_file(action: str, source: str, destination: str = "") -> str:
    """Perform a file system operation.

    Args:
        action: One of 'move', 'rename', 'copy', 'delete'.
        source: Source file path.
        destination: Destination path (not needed for delete).

    Returns:
        Description of what was done.
    """
    source = os.path.expanduser(source)

    if not os.path.exists(source):
        raise ValueError(f"Source does not exist: {source}")

    _check_safety(source)
    if destination:
        destination = os.path.expanduser(destination)
        _validate_write_path(destination)

    if action == "move":
        if not destination:
            raise ValueError("Destination required for move")
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        shutil.move(source, destination)
        return f"Moved {source} → {destination}"

    elif action == "rename":
        if not destination:
            raise ValueError("New name required for rename")
        # If destination is just a filename (no path), rename in same directory
        if not os.path.dirname(destination):
            destination = os.path.join(os.path.dirname(source), destination)
        os.rename(source, destination)
        return f"Renamed {os.path.basename(source)} → {os.path.basename(destination)}"

    elif action == "copy":
        if not destination:
            raise ValueError("Destination required for copy")
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        if os.path.isdir(source):
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        return f"Copied {source} → {destination}"

    elif action == "delete":
        if os.path.isdir(source):
            raise ValueError(f"Refusing to delete directory {source}. Use specific file paths.")
        os.remove(source)
        return f"Deleted {source}"

    else:
        raise ValueError(f"Unknown action '{action}'. Use move, rename, copy, or delete.")


def move_file(src: str, dst: str) -> str:
    """Move a file to a new location. Returns description."""
    return manage_file("move", src, dst)


def _check_safety(path: str) -> None:
    """Raise ValueError if path is in a protected system directory.

    Uses realpath to resolve symlinks (prevents symlink bypass attacks).
    Protects the entire subtree of each protected directory.
    """
    real_path = os.path.realpath(path)

    for protected in PROTECTED_DIRS:
        if real_path == protected or real_path.startswith(protected + os.sep):
            raise ValueError(f"Refusing to modify protected system path: {real_path}")
