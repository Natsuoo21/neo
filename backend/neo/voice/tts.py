"""Text-to-Speech — pyttsx3 voice output.

Provides offline TTS via pyttsx3 (uses platform-native speech engines:
SAPI5 on Windows, NSSpeechSynthesizer on macOS, espeak on Linux).

Usage::

    tts = NeoTTS()
    tts.speak("Hello, I'm Neo.")
"""

import logging
import queue
import threading
from typing import Any

logger = logging.getLogger(__name__)


def _check_pyttsx3() -> Any:
    """Lazily import pyttsx3, raising clear error if unavailable."""
    try:
        import pyttsx3
        return pyttsx3
    except ImportError:
        raise ImportError(
            "pyttsx3 is not installed. Install it with: pip install pyttsx3"
        )


class NeoTTS:
    """Text-to-speech engine using pyttsx3.

    Thread-safe — speak() can be called from any thread.
    Audio is queued and spoken sequentially in a background thread.

    Attributes:
        enabled: Whether TTS output is active.
        rate: Speech rate in words per minute (default: 175).
        volume: Volume 0.0–1.0 (default: 0.9).
    """

    def __init__(
        self,
        rate: int = 175,
        volume: float = 0.9,
        voice_id: str | None = None,
    ) -> None:
        self.enabled = True
        self.rate = rate
        self.volume = volume
        self.voice_id = voice_id
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._speaking = False
        self._thread: threading.Thread | None = None
        self._engine: Any = None
        self._lock = threading.Lock()

    @property
    def speaking(self) -> bool:
        return self._speaking

    def _ensure_engine(self) -> Any:
        """Initialize pyttsx3 engine (must be called in the worker thread)."""
        if self._engine is None:
            pyttsx3 = _check_pyttsx3()
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            self._engine.setProperty("volume", self.volume)
            if self.voice_id:
                self._engine.setProperty("voice", self.voice_id)
        return self._engine

    def speak(self, text: str) -> None:
        """Queue text for speech output.

        If the TTS worker thread is not running, starts it.
        """
        if not self.enabled or not text.strip():
            return

        self._queue.put(text)
        self._start_worker()

    def stop(self) -> None:
        """Stop speaking and clear the queue.

        Drains the queue and sends a sentinel to stop the worker.
        Does NOT call engine.stop() from a foreign thread — pyttsx3
        engines are single-threaded and must only be touched by
        the worker thread.
        """
        # Drain pending items
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        # Send sentinel to stop worker gracefully
        self._queue.put(None)
        self._speaking = False

    def set_rate(self, rate: int) -> None:
        """Update speech rate."""
        self.rate = rate
        if self._engine:
            self._engine.setProperty("rate", rate)

    def set_volume(self, volume: float) -> None:
        """Update volume (0.0–1.0)."""
        self.volume = max(0.0, min(1.0, volume))
        if self._engine:
            self._engine.setProperty("volume", self.volume)

    def set_voice(self, voice_id: str) -> None:
        """Change the voice."""
        self.voice_id = voice_id
        if self._engine:
            self._engine.setProperty("voice", voice_id)

    def get_available_voices(self) -> list[dict]:
        """List available system voices.

        Only safe to call after the worker has initialized the engine.
        If the engine hasn't been created yet, returns an empty list
        rather than creating it on the wrong thread.
        """
        if self._engine is None:
            return []
        try:
            voices = self._engine.getProperty("voices")
            return [
                {"id": v.id, "name": v.name, "languages": getattr(v, "languages", [])}
                for v in voices
            ]
        except Exception:
            logger.exception("Failed to list voices")
            return []

    def get_status(self) -> dict:
        """Return current TTS status."""
        return {
            "enabled": self.enabled,
            "speaking": self.speaking,
            "rate": self.rate,
            "volume": self.volume,
            "voice_id": self.voice_id,
            "queue_size": self._queue.qsize(),
        }

    def _start_worker(self) -> None:
        """Start the background TTS worker if not already running."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def _worker(self) -> None:
        """Background thread that processes the speak queue."""
        try:
            engine = self._ensure_engine()
        except ImportError:
            logger.error("pyttsx3 not available for TTS")
            return

        while True:
            try:
                text = self._queue.get(timeout=5)
            except queue.Empty:
                break

            if text is None:
                break

            self._speaking = True
            try:
                engine.say(text)
                engine.runAndWait()
            except (RuntimeError, OSError):
                logger.exception("TTS speak error")
            finally:
                self._speaking = False

        self._speaking = False
