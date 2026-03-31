"""Shared path utilities for all tool modules.

Centralizes path resolution, validation, and the default save directory
so that security checks and bug fixes only need to happen in one place.
"""

import os

# Directories that should NEVER be modified — shared across all tool modules
PROTECTED_DIRS = {
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
    "/lib",
    "/lib64",
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
}

# Sensitive home-directory paths that should never be written to
_SENSITIVE_HOME_DIRS = {".ssh", ".gnupg", ".config"}


def get_default_save_dir() -> str:
    """Return the default save directory, evaluated at call time."""
    return os.path.expanduser(os.environ.get("DEFAULT_SAVE_DIR", "~/Documents/Neo"))


def resolve_path(title: str, extension: str) -> str:
    """Resolve a title to a safe, validated absolute file path.

    - Expands ~ to home directory
    - If absolute, validates it falls within the user's home or save dir
    - If relative, sanitizes and places in default save directory
    """
    # Expand ~ before checking if absolute
    expanded = os.path.expanduser(title)

    if os.path.isabs(expanded):
        if not expanded.endswith(extension):
            expanded += extension
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
    """Ensure an absolute write path is safe.

    Blocks:
    1. System directories (/, /bin, /etc, etc.)
    2. Sensitive home subdirectories (~/.ssh, ~/.gnupg, ~/.config)
    3. Paths outside the user's home directory or configured save dir

    Raises ValueError if the path is outside allowed boundaries.
    """
    real_path = os.path.realpath(path)

    # Block system directories
    for blocked_dir in PROTECTED_DIRS:
        if real_path == blocked_dir or real_path.startswith(blocked_dir + os.sep):
            raise ValueError(f"Refusing to write to protected system path: {real_path}")

    # Block sensitive home subdirectories
    home = os.path.expanduser("~")
    for sensitive in _SENSITIVE_HOME_DIRS:
        sensitive_path = os.path.join(home, sensitive)
        if real_path == sensitive_path or real_path.startswith(sensitive_path + os.sep):
            raise ValueError(f"Refusing to write to sensitive directory: {real_path}")

    # Ensure the path is under the user's home, configured save dir, or /tmp
    save_dir = os.path.realpath(get_default_save_dir())
    real_home = os.path.realpath(home)
    allowed_prefixes = [real_home + os.sep, save_dir + os.sep, "/tmp" + os.sep]
    if not any(real_path.startswith(prefix) for prefix in allowed_prefixes):
        raise ValueError(f"Path is outside allowed directories: {real_path}")
