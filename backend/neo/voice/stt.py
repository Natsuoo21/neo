"""Speech-to-Text — Local Whisper integration.

Uses OpenAI's Whisper model for offline speech recognition.
Supports microphone input with voice activity detection (VAD)
via webrtcvad (Google's lightweight C-based VAD).

Dependencies (optional — only needed when voice is used):
    pip install openai-whisper sounddevice numpy webrtcvad

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
from collections import deque
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Audio format
_SAMPLE_RATE = 16000
_CHANNELS = 1
_WAKE_WORD = "hey neo"

# webrtcvad settings
_VAD_FRAME_MS = 30  # 10, 20, or 30ms frames
_VAD_FRAME_BYTES = int(_SAMPLE_RATE * 2 * _VAD_FRAME_MS / 1000)  # 960 bytes
_VAD_AGGRESSIVENESS = 3  # 0-3, 3 = most aggressive noise filtering

# Recording timing
_SILENCE_DURATION = 2.0  # Seconds of silence to end recording
_MIN_SPEECH_FRAMES = 3  # Minimum speech frames to start recording

# Wake word settings
_WAKE_SPEECH_PAD = 0.3  # Seconds of pre-speech audio in ring buffer
_WAKE_MAX_UTTERANCE = 4.0  # Max seconds for one wake word check
_WAKE_SILENCE_FRAMES = 33  # ~1s silence to end wake word capture

_SILENCE_THRESHOLD = 500  # Legacy (kept for backward compat)


# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------


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


def _check_webrtcvad() -> Any:
    """Lazily import webrtcvad."""
    try:
        import webrtcvad

        return webrtcvad
    except ImportError:
        raise ImportError(
            "webrtcvad is not installed. Install it with: pip install webrtcvad"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _float32_to_int16_bytes(float_data: Any, np: Any) -> bytes:
    """Convert float32 numpy audio to int16 PCM bytes."""
    int16 = (float_data * 32767).astype(np.int16)
    return int16.tobytes()


def _create_vad(aggressiveness: int = _VAD_AGGRESSIVENESS) -> Any:
    """Create a configured webrtcvad.Vad instance."""
    webrtcvad = _check_webrtcvad()
    vad = webrtcvad.Vad()
    vad.set_mode(aggressiveness)
    return vad


def _is_speech_frame(vad: Any, pcm_bytes: bytes) -> bool:
    """Check if a PCM frame contains speech using webrtcvad."""
    return vad.is_speech(pcm_bytes, _SAMPLE_RATE)


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
        """Load the Whisper model into memory."""
        whisper = _check_whisper()
        name = model_name or self.model_name
        logger.info("Loading Whisper model: %s", name)
        self._model = whisper.load_model(name)
        self.model_name = name
        logger.info("Whisper model '%s' loaded", name)

    def transcribe(self, audio_path: str | Path) -> str:
        """Transcribe an audio file to text."""
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
        """Transcribe raw PCM audio data (16-bit, 16kHz, mono)."""
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
                with wave.open(tmp, "wb") as wf:
                    wf.setnchannels(_CHANNELS)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(_SAMPLE_RATE)
                    wf.writeframes(audio_data)
            return self.transcribe(tmp_path)
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    def start_recording(self, on_transcription: Callable[[str], None]) -> None:
        """Start recording from microphone with VAD.

        Records until silence is detected, then transcribes and calls
        the callback with the result.
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
        """Record audio from mic using webrtcvad for silence detection."""
        sd = _check_sounddevice()
        np = _check_numpy()
        vad = _create_vad()

        frames: list[bytes] = []
        speech_detected = False
        speech_frame_count = 0
        silence_start: float | None = None
        stream_done = threading.Event()

        # blocksize = 480 samples = one 30ms VAD frame at 16kHz
        blocksize = int(_SAMPLE_RATE * _VAD_FRAME_MS / 1000)

        def callback(indata: Any, frame_count: int, time_info: Any, status: Any) -> None:
            nonlocal speech_detected, speech_frame_count, silence_start

            if not self._recording:
                raise sd.CallbackAbort

            pcm_bytes = _float32_to_int16_bytes(indata, np)
            frames.append(pcm_bytes)

            is_speech = _is_speech_frame(vad, pcm_bytes)

            if is_speech:
                speech_frame_count += 1
                silence_start = None
                if speech_frame_count >= _MIN_SPEECH_FRAMES:
                    speech_detected = True
            elif speech_detected:
                # Silence after speech — start/continue grace period
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= _SILENCE_DURATION:
                    stream_done.set()
                    raise sd.CallbackAbort

        try:
            with sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=_CHANNELS,
                dtype="float32",
                callback=callback,
                blocksize=blocksize,
            ):
                while self._recording and not stream_done.is_set():
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

        audio_bytes = b"".join(frames)

        try:
            text = self.transcribe_audio_data(audio_bytes)
            if text and self._on_transcription:
                self._on_transcription(text)
        except Exception:
            logger.exception("Transcription error")

    def _wake_word_loop(self) -> None:
        """Continuously listen for wake word using webrtcvad, then record."""
        sd = _check_sounddevice()
        np = _check_numpy()
        vad = _create_vad()

        logger.info("Wake word monitoring started (listening for '%s')", _WAKE_WORD)

        blocksize = int(_SAMPLE_RATE * _VAD_FRAME_MS / 1000)
        # Ring buffer for pre-speech padding
        pad_frames = int(_WAKE_SPEECH_PAD * 1000 / _VAD_FRAME_MS)
        ring_buffer: deque[bytes] = deque(maxlen=pad_frames)

        max_frames = int(_WAKE_MAX_UTTERANCE * 1000 / _VAD_FRAME_MS)

        try:
            with sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=_CHANNELS,
                dtype="float32",
                blocksize=blocksize,
            ) as stream:
                while self._wake_word_active:
                    # Read one VAD frame
                    data, _overflowed = stream.read(blocksize)
                    pcm_bytes = _float32_to_int16_bytes(data, np)

                    if not _is_speech_frame(vad, pcm_bytes):
                        ring_buffer.append(pcm_bytes)
                        continue

                    # Speech detected — collect utterance
                    utterance_frames: list[bytes] = list(ring_buffer)
                    utterance_frames.append(pcm_bytes)
                    silence_count = 0

                    while (
                        self._wake_word_active
                        and len(utterance_frames) < max_frames
                    ):
                        data, _overflowed = stream.read(blocksize)
                        pcm_bytes = _float32_to_int16_bytes(data, np)
                        utterance_frames.append(pcm_bytes)

                        if _is_speech_frame(vad, pcm_bytes):
                            silence_count = 0
                        else:
                            silence_count += 1
                            if silence_count >= _WAKE_SILENCE_FRAMES:
                                break

                    # Transcribe the speech segment
                    audio_bytes = b"".join(utterance_frames)
                    try:
                        text = self.transcribe_audio_data(audio_bytes)
                    except Exception:
                        logger.exception("Wake word transcription error")
                        ring_buffer.clear()
                        continue

                    if _WAKE_WORD in text.lower():
                        logger.info("Wake word detected!")
                        self._recording = True
                        self._record_loop()

                    ring_buffer.clear()

        except Exception:
            logger.exception("Wake word stream error")

        logger.info("Wake word monitoring stopped")

    def get_status(self) -> dict:
        """Return current STT status."""
        try:
            _check_webrtcvad()
            vad_available = True
        except ImportError:
            vad_available = False

        return {
            "model_loaded": self.model_loaded,
            "model_name": self.model_name,
            "recording": self.recording,
            "wake_word_active": self.wake_word_active,
            "language": self.language,
            "vad_available": vad_available,
        }
