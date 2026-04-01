"""Speech-to-Text — Local Whisper integration.

Uses OpenAI's Whisper model for offline speech recognition.
Supports microphone input with voice activity detection (VAD)
via silence-based segmentation.

Dependencies (optional — only needed when voice is used):
    pip install openai-whisper sounddevice numpy

Usage::

    stt = WhisperSTT()
    stt.load_model("base")
    text = stt.transcribe("/path/to/audio.wav")
"""

import logging
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Default VAD settings
_SILENCE_THRESHOLD = 500  # RMS threshold for silence detection
_SILENCE_DURATION = 2.0  # Seconds of silence to end recording
_SAMPLE_RATE = 16000
_CHANNELS = 1
_WAKE_WORD = "hey neo"


def _check_whisper() -> Any:
    """Lazily import whisper, raising clear error if unavailable."""
    try:
        import whisper
        return whisper
    except ImportError:
        raise ImportError(
            "openai-whisper is not installed. Install it with: pip install openai-whisper"
        )


def _check_sounddevice() -> Any:
    """Lazily import sounddevice."""
    try:
        import sounddevice
        return sounddevice
    except ImportError:
        raise ImportError(
            "sounddevice is not installed. Install it with: pip install sounddevice"
        )


def _check_numpy() -> Any:
    """Lazily import numpy."""
    try:
        import numpy
        return numpy
    except ImportError:
        raise ImportError("numpy is not installed. Install it with: pip install numpy")


class WhisperSTT:
    """Speech-to-text engine using OpenAI Whisper (local).

    Attributes:
        model_name: Whisper model size (tiny, base, small, medium, large).
        language: Language hint for transcription.
    """

    def __init__(
        self,
        model_name: str = "base",
        language: str = "en",
    ) -> None:
        self.model_name = model_name
        self.language = language
        self._model: Any = None
        self._recording = False
        self._wake_word_active = False
        self._record_thread: threading.Thread | None = None
        self._wake_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._on_transcription: Callable[[str], None] | None = None

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def wake_word_active(self) -> bool:
        return self._wake_word_active

    def load_model(self, model_name: str | None = None) -> None:
        """Load the Whisper model into memory.

        Args:
            model_name: Override the model size (tiny/base/small/medium/large).
        """
        whisper = _check_whisper()
        name = model_name or self.model_name
        logger.info("Loading Whisper model: %s", name)
        self._model = whisper.load_model(name)
        self.model_name = name
        logger.info("Whisper model '%s' loaded", name)

    def transcribe(self, audio_path: str | Path) -> str:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to a WAV/MP3/FLAC audio file.

        Returns:
            Transcribed text string.
        """
        if self._model is None:
            self.load_model()

        result = self._model.transcribe(
            str(audio_path),
            language=self.language,
            fp16=False,
        )
        text = result.get("text", "").strip()
        logger.info("Transcribed: %s", text[:80])
        return text

    def transcribe_audio_data(self, audio_data: bytes) -> str:
        """Transcribe raw PCM audio data (16-bit, 16kHz, mono).

        Writes to a temp WAV file, then transcribes.
        """
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            with wave.open(tmp, "wb") as wf:
                wf.setnchannels(_CHANNELS)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(_SAMPLE_RATE)
                wf.writeframes(audio_data)

        try:
            return self.transcribe(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def start_recording(self, on_transcription: Callable[[str], None]) -> None:
        """Start recording from microphone with VAD.

        Records until silence is detected, then transcribes and calls
        the callback with the result.

        Args:
            on_transcription: Called with transcribed text when speech ends.
        """
        if self._recording:
            return

        self._on_transcription = on_transcription
        self._recording = True
        self._record_thread = threading.Thread(
            target=self._record_loop,
            daemon=True,
        )
        self._record_thread.start()

    def stop_recording(self) -> None:
        """Stop the recording loop."""
        self._recording = False
        if self._record_thread and self._record_thread.is_alive():
            self._record_thread.join(timeout=3)
        self._record_thread = None

    def start_wake_word(self, on_transcription: Callable[[str], None]) -> None:
        """Start continuous low-power wake word monitoring.

        Listens for "Hey Neo" and then records a full utterance.
        """
        if self._wake_word_active:
            return

        self._on_transcription = on_transcription
        self._wake_word_active = True
        self._wake_thread = threading.Thread(
            target=self._wake_word_loop,
            daemon=True,
        )
        self._wake_thread.start()

    def stop_wake_word(self) -> None:
        """Stop wake word monitoring."""
        self._wake_word_active = False
        self._recording = False
        if self._wake_thread and self._wake_thread.is_alive():
            self._wake_thread.join(timeout=3)
        self._wake_thread = None

    def _record_loop(self) -> None:
        """Record audio from mic, detect silence, transcribe."""
        sd = _check_sounddevice()
        np = _check_numpy()

        frames: list = []
        silence_start: float | None = None

        def callback(indata, frame_count, time_info, status):
            if not self._recording:
                raise sd.CallbackAbort
            frames.append(indata.copy())

            # RMS-based silence detection
            rms = np.sqrt(np.mean(indata ** 2)) * 32768
            nonlocal silence_start
            if rms < _SILENCE_THRESHOLD:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= _SILENCE_DURATION:
                    raise sd.CallbackAbort
            else:
                silence_start = None

        try:
            with sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=_CHANNELS,
                dtype="float32",
                callback=callback,
                blocksize=1024,
            ):
                while self._recording:
                    time.sleep(0.1)
        except sd.CallbackAbort:
            pass
        except Exception:
            logger.exception("Recording error")
            self._recording = False
            return

        self._recording = False

        if not frames:
            return

        # Convert float32 frames to int16 bytes
        audio_array = np.concatenate(frames, axis=0)
        audio_int16 = (audio_array * 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()

        try:
            text = self.transcribe_audio_data(audio_bytes)
            if text and self._on_transcription:
                self._on_transcription(text)
        except Exception:
            logger.exception("Transcription error")

    def _wake_word_loop(self) -> None:
        """Continuously listen for wake word, then record full utterance."""
        sd = _check_sounddevice()
        np = _check_numpy()

        logger.info("Wake word monitoring started (listening for '%s')", _WAKE_WORD)

        while self._wake_word_active:
            # Record a short chunk (3 seconds) for wake word detection
            try:
                audio = sd.rec(
                    int(3 * _SAMPLE_RATE),
                    samplerate=_SAMPLE_RATE,
                    channels=_CHANNELS,
                    dtype="float32",
                )
                sd.wait()
            except Exception:
                logger.exception("Wake word recording error")
                time.sleep(1)
                continue

            if not self._wake_word_active:
                break

            # Convert to int16 and transcribe
            audio_int16 = (audio * 32767).astype(np.int16)
            audio_bytes = audio_int16.tobytes()

            try:
                text = self.transcribe_audio_data(audio_bytes)
            except Exception:
                continue

            if _WAKE_WORD in text.lower():
                logger.info("Wake word detected!")
                # Record the actual command
                self._recording = True
                self._record_loop()

        logger.info("Wake word monitoring stopped")

    def get_status(self) -> dict:
        """Return current STT status."""
        return {
            "model_loaded": self.model_loaded,
            "model_name": self.model_name,
            "recording": self.recording,
            "wake_word_active": self.wake_word_active,
            "language": self.language,
        }
