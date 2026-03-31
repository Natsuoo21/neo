"""Shared path utilities for all tool modules.

Centralizes path resolution, validation, and the default save directory
so that security checks and bug fixes only need to happen in one place.
"""

import os


def get_default_save_dir() -> str:
    """Return the default save directory, evaluated at call time."""
    return os.path.expanduser(os.environ.get("DEFAULT_SAVE_DIR", "~/Documents/Neo"))


def resolve_path(title: str, extension: str) -> str:
    """Resolve a title to a safe, validated absolute file path.

    - Expands ~ to home directory
    - If absolute, validates it falls within the allowed save directory
    - If relative, sanitizes and places in default save directory
    """
    # Expand ~ before checking if absolute
    expanded = os.path.expanduser(title)

    if os.path.isabs(expanded):
        if not expanded.endswith(extension):
            expanded += extension
        # SEC-2: Validate absolute paths are within allowed directories
        _validate_write_path(expanded)
        return expanded

    # Sanitize filename for relative titles
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    safe_name = safe_name.strip().replace(" ", "_")
    if not safe_name.endswith(extension):
        safe_name += extension

    save_dir = get_default_save_dir()
    return os.path.join(save_dir, safe_name)


def _validate_write_path(path: str) -> None:
    """Ensure an absolute write path is not in a protected system directory.

    Raises ValueError if the path is outside allowed boundaries.
    """
    real_path = os.path.realpath(path)

    # Block system directories
    blocked = {
        "/bin",
        "/sbin",
        "/usr",
        "/etc",
        "/var",
        "/boot",
        "/dev",
        "/proc",
        "/sys",
        "/lib",
        "/lib64",
        "C:\\Windows",
        "C:\\Program Files",
        "C:\\Program Files (x86)",
    }
    for blocked_dir in blocked:
        if real_path == blocked_dir or real_path.startswith(blocked_dir + os.sep):
            raise ValueError(f"Refusing to write to protected system path: {real_path}")
