"""Skill hot-reload — Watch skill directories for changes.

Uses watchdog to monitor skills/public/ and skills/user/ directories.
When a .md file is created, modified, or deleted, re-syncs skills to DB.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "public")
_USER_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "user")


class _SkillFileHandler(FileSystemEventHandler):
    """Handles .md file events in skill directories."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()

    def _sync(self) -> None:
        """Re-sync all skills to DB."""
        with self._lock:
            try:
                from neo.memory.db import get_session
                from neo.skills.loader import sync_skills_to_db

                with get_session(self._db_path) as conn:
                    count = sync_skills_to_db(conn)
                    logger.info("Hot-reload: synced %d skills", count)
            except Exception:
                logger.exception("Hot-reload: failed to sync skills")

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            logger.info("Skill file created: %s", event.src_path)
            self._sync()

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            logger.info("Skill file modified: %s", event.src_path)
            self._sync()

    def on_deleted(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            logger.info("Skill file deleted: %s", event.src_path)
            self._sync()


class SkillWatcher:
    """Watches skill directories and hot-reloads on changes."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._observer: Any = None

    def start(self) -> None:
        """Start watching skill directories (non-blocking, runs in background thread)."""
        handler = _SkillFileHandler(self._db_path)
        self._observer = Observer()

        for skill_dir in [_SKILLS_DIR, _USER_SKILLS_DIR]:
            if os.path.isdir(skill_dir):
                self._observer.schedule(handler, skill_dir, recursive=False)
                logger.info("Watching skill directory: %s", skill_dir)

        self._observer.daemon = True
        self._observer.start()

    def stop(self) -> None:
        """Stop watching."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()
