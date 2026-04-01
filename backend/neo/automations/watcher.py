"""File watcher — watchdog-based file system monitoring.

Watches directories for file events and triggers automations
with debouncing to prevent duplicate triggers.
"""

import fnmatch
import json
import logging
import threading
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from neo.automations.safety import is_globally_paused
from neo.memory.db import get_session
from neo.memory.models import get_automations_by_trigger

logger = logging.getLogger(__name__)

# Debounce interval in seconds
_DEBOUNCE_SECONDS = 2.0


class DebouncedHandler(FileSystemEventHandler):
    """File system event handler with debouncing.

    Prevents duplicate triggers when editors save files multiple times
    (e.g., write temp file + rename).
    """

    def __init__(
        self,
        automation_id: int,
        pattern: str,
        event_types: list[str],
        callback: Callable[[int, str, FileSystemEvent], None],
        debounce_seconds: float = _DEBOUNCE_SECONDS,
    ):
        super().__init__()
        self.automation_id = automation_id
        self.pattern = pattern
        self.event_types = event_types
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Handle any file system event with debouncing."""
        # Skip directory events
        if event.is_directory:
            return

        # Skip if globally paused (RULE 5)
        if is_globally_paused():
            return

        # Check event type matches
        event_type = event.event_type  # created, modified, deleted, moved
        if event_type not in self.event_types:
            return

        # Check file pattern matches
        src_path = str(event.src_path)
        filename = src_path.rsplit("/", 1)[-1] if "/" in src_path else src_path.rsplit("\\", 1)[-1]
        if not fnmatch.fnmatch(filename, self.pattern):
            return

        # Debounce: cancel previous timer for this path, schedule new one
        with self._lock:
            key = f"{src_path}:{event_type}"
            existing = self._timers.get(key)
            if existing:
                existing.cancel()

            timer = threading.Timer(
                self.debounce_seconds,
                self._fire,
                args=[src_path, event],
            )
            self._timers[key] = timer
            timer.start()

    def _fire(self, src_path: str, event: FileSystemEvent) -> None:
        """Actually trigger the callback after debounce."""
        with self._lock:
            key = f"{src_path}:{event.event_type}"
            self._timers.pop(key, None)

        try:
            self.callback(self.automation_id, src_path, event)
        except Exception:
            logger.exception("Watcher callback failed for automation %d", self.automation_id)

    def cancel_all(self) -> None:
        """Cancel all pending debounce timers."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()


class NeoFileWatcher:
    """Manages file system watchers for file_event automations."""

    def __init__(
        self,
        db_path: str,
        execute_callback: Callable[[int, str], None],
    ):
        self._db_path = db_path
        self._execute_callback = execute_callback
        self._observer = Observer()
        # Maps automation_id -> (handler, watch_object)
        self._handlers: dict[int, tuple[DebouncedHandler, object]] = {}

    def start(self) -> None:
        """Load enabled file_event automations from DB and start watching."""
        with get_session(self._db_path) as conn:
            automations = get_automations_by_trigger(conn, "file_event")

        for auto in automations:
            config = json.loads(auto.get("trigger_config", "{}") or "{}")
            path = config.get("path", "")
            pattern = config.get("pattern", "*")
            event_types = config.get("event_types", ["created", "modified"])

            if path:
                self.add_watcher(auto["id"], path, pattern, event_types)

        self._observer.start()
        logger.info("File watcher started with %d watchers", len(self._handlers))

    def shutdown(self) -> None:
        """Stop all watchers and cleanup."""
        # Cancel all debounce timers
        for handler, _ in self._handlers.values():
            handler.cancel_all()

        self._observer.stop()
        self._observer.join(timeout=5)
        logger.info("File watcher shut down")

    def add_watcher(
        self,
        automation_id: int,
        path: str,
        pattern: str = "*",
        event_types: list[str] | None = None,
    ) -> None:
        """Add a file watcher for an automation."""
        if event_types is None:
            event_types = ["created", "modified"]

        # Remove existing watcher for this automation
        self.remove_watcher(automation_id)

        handler = DebouncedHandler(
            automation_id=automation_id,
            pattern=pattern,
            event_types=event_types,
            callback=self._on_event,
        )

        try:
            watch = self._observer.schedule(handler, path, recursive=False)
            self._handlers[automation_id] = (handler, watch)
            logger.info(
                "Watching %s for automation %d (pattern=%s, events=%s)",
                path, automation_id, pattern, event_types,
            )
        except (FileNotFoundError, OSError) as e:
            logger.error("Failed to watch %s for automation %d: %s", path, automation_id, e)

    def remove_watcher(self, automation_id: int) -> None:
        """Remove a file watcher for an automation."""
        entry = self._handlers.pop(automation_id, None)
        if entry:
            handler, watch = entry
            handler.cancel_all()
            try:
                self._observer.unschedule(watch)  # type: ignore[arg-type]
            except Exception:
                pass  # Already unscheduled
            logger.info("Removed watcher for automation %d", automation_id)

    def _on_event(self, automation_id: int, src_path: str, event: FileSystemEvent) -> None:
        """Handle a matched file event by executing the automation command."""
        logger.info(
            "File event: %s %s (automation %d)",
            event.event_type, src_path, automation_id,
        )
        # Execute the automation command via the callback
        with get_session(self._db_path) as conn:
            from neo.memory.models import get_automation
            auto = get_automation(conn, automation_id)
            if auto and auto.get("is_enabled"):
                self._execute_callback(automation_id, auto["command"])
