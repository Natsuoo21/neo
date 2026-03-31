"""File system tool — Move, rename, copy, delete, organize files."""

import os
import shutil

# Directories that should NEVER be modified
_PROTECTED_DIRS = {
    "/",
    "/bin",
    "/sbin",
    "/usr",
    "/etc",
    "/var",
    "/boot",
    "/dev",
    "/proc",
    "/sys",
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
}


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
        return f"Error: source does not exist: {source}"

    _check_safety(source)
    if destination:
        destination = os.path.expanduser(destination)
        _check_safety(destination)

    if action == "move":
        if not destination:
            return "Error: destination required for move"
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        shutil.move(source, destination)
        return f"Moved {source} → {destination}"

    elif action == "rename":
        if not destination:
            return "Error: new name required for rename"
        # If destination is just a filename (no path), rename in same directory
        if not os.path.dirname(destination):
            destination = os.path.join(os.path.dirname(source), destination)
        os.rename(source, destination)
        return f"Renamed {os.path.basename(source)} → {os.path.basename(destination)}"

    elif action == "copy":
        if not destination:
            return "Error: destination required for copy"
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        if os.path.isdir(source):
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        return f"Copied {source} → {destination}"

    elif action == "delete":
        if os.path.isdir(source):
            return f"Error: refusing to delete directory {source}. Use specific file paths."
        os.remove(source)
        return f"Deleted {source}"

    else:
        return f"Error: unknown action '{action}'. Use move, rename, copy, or delete."


def move_file(src: str, dst: str) -> str:
    """Move a file to a new location. Returns description."""
    return manage_file("move", src, dst)


def _check_safety(path: str) -> None:
    """Raise ValueError if path is in a protected system directory."""
    abs_path = os.path.abspath(path)
    for protected in _PROTECTED_DIRS:
        if abs_path == protected or abs_path.startswith(protected + os.sep):
            if abs_path.count(os.sep) <= protected.count(os.sep) + 1:
                raise ValueError(f"Refusing to modify protected system path: {abs_path}")
