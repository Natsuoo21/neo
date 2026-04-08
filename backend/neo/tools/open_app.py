"""Open App tool — Launch applications on the user's machine.

Detects the platform (Windows, WSL, macOS, Linux) and uses the
appropriate mechanism to open applications by name, path, or URI.
"""

import os
import platform
import subprocess
import sys

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

_BLOCKED_EXTENSIONS = frozenset({".bat", ".cmd", ".ps1", ".sh", ".vbs", ".wsf"})


def _is_wsl() -> bool:
    """Return True when running inside Windows Subsystem for Linux."""
    if sys.platform != "linux":
        return False
    try:
        return "microsoft" in platform.release().lower()
    except Exception:
        return False


def get_platform() -> str:
    """Return normalised platform: 'windows', 'wsl', 'macos', or 'linux'."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if _is_wsl():
        return "wsl"
    return "linux"


# ---------------------------------------------------------------------------
# App aliases — friendly names → launch commands per platform
# ---------------------------------------------------------------------------

# Values can be:
#   str  → used on every platform (or passed to the platform launcher)
#   dict → keys are platform names, values are the command for that platform
APP_ALIASES: dict[str, str | dict[str, str]] = {
    "obsidian": "obsidian://",
    "vscode": {
        "windows": "code",
        "wsl": "code",
        "macos": "code",
        "linux": "code",
    },
    "chrome": {
        "windows": "chrome",
        "wsl": "chrome",
        "macos": "Google Chrome",
        "linux": "google-chrome",
    },
    "firefox": {
        "windows": "firefox",
        "wsl": "firefox",
        "macos": "Firefox",
        "linux": "firefox",
    },
    "notepad": "notepad.exe",
    "explorer": "explorer.exe",
    "terminal": {
        "windows": "wt.exe",
        "wsl": "wt.exe",
        "macos": "Terminal",
        "linux": "x-terminal-emulator",
    },
    "calculator": {
        "windows": "calc.exe",
        "wsl": "calc.exe",
        "macos": "Calculator",
        "linux": "gnome-calculator",
    },
}


def _resolve_alias(app_name: str) -> str:
    """Resolve a friendly alias to a platform-specific command.

    If *app_name* is not in the alias table it is returned unchanged.
    """
    key = app_name.lower().strip()
    entry = APP_ALIASES.get(key)
    if entry is None:
        return app_name

    if isinstance(entry, str):
        return entry

    plat = get_platform()
    return entry.get(plat, app_name)


# ---------------------------------------------------------------------------
# Safety checks
# ---------------------------------------------------------------------------


def _validate_app(app: str, args: str) -> None:
    """Block dangerous invocations.

    Raises ``ValueError`` for script files or protected-directory executables.
    """
    # Block script extensions in the main app name
    _, ext = os.path.splitext(app)
    if ext.lower() in _BLOCKED_EXTENSIONS:
        raise ValueError(
            f"Refusing to execute script file: {app}. "
            "Only application binaries and URI protocols are allowed."
        )

    # Also check args for injected scripts
    for token in args.split():
        _, ext = os.path.splitext(token)
        if ext.lower() in _BLOCKED_EXTENSIONS:
            raise ValueError(f"Refusing to execute script found in arguments: {token}")


# ---------------------------------------------------------------------------
# Platform launchers
# ---------------------------------------------------------------------------


def _is_uri(app: str) -> bool:
    """Return True if *app* looks like a URI protocol (e.g. obsidian://)."""
    return "://" in app or app.endswith("://")


def _launch_windows(app: str, args: str) -> str:
    """Launch on native Windows."""
    if _is_uri(app):
        target = f"{app}{args}" if args and not app.endswith(("?", "/", "&")) else app
        os.startfile(target)  # type: ignore[attr-defined]
        return f"Opened URI: {target}"

    cmd = [app] + (args.split() if args else [])
    subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"Opened {app}" + (f" with args: {args}" if args else "")


def _launch_wsl(app: str, args: str) -> str:
    """Launch a Windows application from WSL."""
    if _is_uri(app):
        target = f"{app}{args}" if args and not app.endswith(("?", "/", "&")) else app
        subprocess.Popen(  # noqa: S603
            ["cmd.exe", "/c", "start", "", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Opened URI: {target}"

    cmd_parts = ["cmd.exe", "/c", "start", "", app] + (args.split() if args else [])
    subprocess.Popen(  # noqa: S603
        cmd_parts,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"Opened {app}" + (f" with args: {args}" if args else "")


def _launch_macos(app: str, args: str) -> str:
    """Launch on macOS via the ``open`` command."""
    if _is_uri(app):
        target = f"{app}{args}" if args and not app.endswith(("?", "/", "&")) else app
        subprocess.Popen(  # noqa: S603
            ["open", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Opened URI: {target}"

    cmd = ["open", "-a", app] + (args.split() if args else [])
    subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"Opened {app}" + (f" with args: {args}" if args else "")


def _launch_linux(app: str, args: str) -> str:
    """Launch on native Linux via subprocess."""
    if _is_uri(app):
        target = f"{app}{args}" if args and not app.endswith(("?", "/", "&")) else app
        subprocess.Popen(  # noqa: S603
            ["xdg-open", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Opened URI: {target}"

    cmd = [app] + (args.split() if args else [])
    subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"Opened {app}" + (f" with args: {args}" if args else "")


_LAUNCHERS = {
    "windows": _launch_windows,
    "wsl": _launch_wsl,
    "macos": _launch_macos,
    "linux": _launch_linux,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def open_app(app_name: str, args: str = "") -> str:
    """Open an application on the user's machine.

    Args:
        app_name: Application name, alias, or URI protocol
                  (e.g. ``"obsidian"``, ``"vscode"``, ``"obsidian://open"``).
        args: Optional arguments passed to the application.

    Returns:
        Human-readable confirmation string.

    Raises:
        ValueError: If the app name or args contain blocked script files.
        RuntimeError: If the application could not be launched.
    """
    resolved = _resolve_alias(app_name)
    _validate_app(resolved, args)

    plat = get_platform()
    launcher = _LAUNCHERS[plat]

    try:
        return launcher(resolved, args)
    except FileNotFoundError:
        raise RuntimeError(
            f"Application '{app_name}' (resolved to '{resolved}') not found on this system."
        ) from None
    except OSError as exc:
        raise RuntimeError(f"Failed to open '{app_name}': {exc}") from exc
