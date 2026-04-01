"""Tests for neo.voice.stt — Whisper STT engine."""

import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

from neo.voice.stt import _SILENCE_THRESHOLD, _WAKE_WORD, WhisperSTT

# ---------------------------------------------------------------------------
# WhisperSTT — basic state
# ---------------------------------------------------------------------------


class TestWhisperSTTState:
    def test_initial_state(self):
        stt = WhisperSTT()
        assert stt.model_name == "base"
        assert stt.language == "en"
        assert stt.model_loaded is False
        assert stt.recording is False
        assert stt.wake_word_active is False

    def test_custom_init(self):
        stt = WhisperSTT(model_name="tiny", language="pt")
        assert stt.model_name == "tiny"
        assert stt.language == "pt"

    def test_get_status(self):
        stt = WhisperSTT(model_name="small", language="ja")
        status = stt.get_status()
        assert status["model_loaded"] is False
        assert status["model_name"] == "small"
        assert status["recording"] is False
        assert status["wake_word_active"] is False
        assert status["language"] == "ja"


# ---------------------------------------------------------------------------
# WhisperSTT — transcribe with mock
# ---------------------------------------------------------------------------


class TestWhisperSTTTranscribe:
    def _make_wav(self, tmp_path: Path, duration_s: float = 0.5) -> str:
        """Create a valid WAV file with silence."""
        wav_path = str(tmp_path / "test.wav")
        n_samples = int(16000 * duration_s)
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * n_samples)
        return wav_path

    @patch("neo.voice.stt._check_whisper")
    def test_transcribe_file(self, mock_check, tmp_path: Path):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "hello world"}
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_check.return_value = mock_whisper

        stt = WhisperSTT()
        stt.load_model()

        wav_path = self._make_wav(tmp_path)
        result = stt.transcribe(wav_path)
        assert result == "hello world"
        mock_model.transcribe.assert_called_once()

    @patch("neo.voice.stt._check_whisper")
    def test_transcribe_auto_loads_model(self, mock_check, tmp_path: Path):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "auto loaded"}
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_check.return_value = mock_whisper

        stt = WhisperSTT()
        wav_path = self._make_wav(tmp_path)
        result = stt.transcribe(wav_path)
        assert result == "auto loaded"
        mock_whisper.load_model.assert_called_once()

    @patch("neo.voice.stt._check_whisper")
    def test_transcribe_audio_data(self, mock_check, tmp_path: Path):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "from bytes"}
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_check.return_value = mock_whisper

        stt = WhisperSTT()
        stt.load_model()

        # 0.1 seconds of silence (16kHz, 16-bit mono)
        n_samples = 1600
        audio_bytes = b"\x00\x00" * n_samples
        result = stt.transcribe_audio_data(audio_bytes)
        assert result == "from bytes"

    @patch("neo.voice.stt._check_whisper")
    def test_load_model_override(self, mock_check):
        mock_whisper = MagicMock()
        mock_check.return_value = mock_whisper

        stt = WhisperSTT(model_name="base")
        stt.load_model("tiny")
        assert stt.model_name == "tiny"
        mock_whisper.load_model.assert_called_with("tiny")

    @patch("neo.voice.stt._check_whisper")
    def test_transcribe_empty_result(self, mock_check, tmp_path: Path):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "  "}
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_check.return_value = mock_whisper

        stt = WhisperSTT()
        stt.load_model()
        wav_path = self._make_wav(tmp_path)
        result = stt.transcribe(wav_path)
        assert result == ""


# ---------------------------------------------------------------------------
# WhisperSTT — recording controls (no audio hardware needed)
# ---------------------------------------------------------------------------


class TestWhisperSTTRecording:
    def test_start_stop_recording(self):
        """Verify start/stop recording flags without actual audio."""
        stt = WhisperSTT()

        # Patch the record thread to just set the flag
        def fake_record():
            pass

        stt._record_loop = fake_record
        stt.start_recording(lambda t: None)
        assert stt.recording is True

        stt.stop_recording()
        assert stt.recording is False

    def test_start_recording_idempotent(self):
        stt = WhisperSTT()
        stt._record_loop = lambda: None

        def noop_cb(t):
            pass

        stt.start_recording(noop_cb)
        stt.start_recording(noop_cb)  # Should not create another thread
        stt.stop_recording()

    def test_stop_when_not_recording(self):
        stt = WhisperSTT()
        stt.stop_recording()  # Should not raise

    def test_start_stop_wake_word(self):
        stt = WhisperSTT()
        stt._wake_word_loop = lambda: None
        stt.start_wake_word(lambda t: None)
        assert stt.wake_word_active is True
        stt.stop_wake_word()
        assert stt.wake_word_active is False

    def test_stop_wake_word_when_not_active(self):
        stt = WhisperSTT()
        stt.stop_wake_word()  # Should not raise


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestSTTConstants:
    def test_wake_word(self):
        assert _WAKE_WORD == "hey neo"

    def test_silence_threshold_positive(self):
        assert _SILENCE_THRESHOLD > 0
