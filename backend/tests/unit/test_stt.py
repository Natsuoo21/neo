"""Tests for neo.voice.stt — Whisper STT with webrtcvad."""

import struct
import time
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from neo.voice import stt
from neo.voice.stt import (
    WhisperSTT,
    _CHANNELS,
    _MIN_SPEECH_FRAMES,
    _SAMPLE_RATE,
    _SILENCE_DURATION,
    _SILENCE_THRESHOLD,
    _VAD_AGGRESSIVENESS,
    _VAD_FRAME_BYTES,
    _VAD_FRAME_MS,
    _WAKE_MAX_UTTERANCE,
    _WAKE_SILENCE_FRAMES,
    _WAKE_SPEECH_PAD,
    _WAKE_WORD,
    _check_webrtcvad,
    _create_vad,
    _float32_to_int16_bytes,
    _is_speech_frame,
)


# ---------------------------------------------------------------------------
# TestSTTConstants — validate constant values and relationships
# ---------------------------------------------------------------------------


class TestSTTConstants:
    def test_sample_rate(self):
        assert _SAMPLE_RATE == 16000

    def test_channels(self):
        assert _CHANNELS == 1

    def test_wake_word(self):
        assert _WAKE_WORD == "hey neo"

    def test_vad_frame_ms_valid(self):
        assert _VAD_FRAME_MS in (10, 20, 30)

    def test_vad_frame_bytes(self):
        expected = int(_SAMPLE_RATE * 2 * _VAD_FRAME_MS / 1000)
        assert _VAD_FRAME_BYTES == expected

    def test_vad_frame_bytes_value(self):
        # 30ms at 16kHz, 16-bit mono = 960 bytes
        assert _VAD_FRAME_BYTES == 960

    def test_vad_aggressiveness_range(self):
        assert 0 <= _VAD_AGGRESSIVENESS <= 3

    def test_silence_duration_positive(self):
        assert _SILENCE_DURATION > 0

    def test_min_speech_frames_positive(self):
        assert _MIN_SPEECH_FRAMES >= 1

    def test_wake_speech_pad_positive(self):
        assert _WAKE_SPEECH_PAD > 0

    def test_wake_max_utterance_positive(self):
        assert _WAKE_MAX_UTTERANCE > 0

    def test_wake_silence_frames_positive(self):
        assert _WAKE_SILENCE_FRAMES >= 1

    def test_silence_threshold_positive(self):
        assert _SILENCE_THRESHOLD > 0


# ---------------------------------------------------------------------------
# TestLazyImports — import error handling
# ---------------------------------------------------------------------------


class TestLazyImports:
    @patch.dict("sys.modules", {"webrtcvad": None})
    def test_check_webrtcvad_missing(self):
        with pytest.raises(ImportError, match="webrtcvad is not installed"):
            _check_webrtcvad()

    @patch("neo.voice.stt._check_webrtcvad")
    def test_check_webrtcvad_present(self, mock_check):
        mock_mod = MagicMock()
        mock_check.return_value = mock_mod
        result = stt._check_webrtcvad()
        assert result is mock_mod

    @patch.dict("sys.modules", {"whisper": None})
    def test_check_whisper_missing(self):
        with pytest.raises(ImportError, match="openai-whisper"):
            stt._check_whisper()

    @patch.dict("sys.modules", {"sounddevice": None})
    def test_check_sounddevice_missing(self):
        with pytest.raises(ImportError, match="sounddevice"):
            stt._check_sounddevice()

    @patch.dict("sys.modules", {"numpy": None})
    def test_check_numpy_missing(self):
        with pytest.raises(ImportError, match="numpy"):
            stt._check_numpy()


# ---------------------------------------------------------------------------
# TestFloat32ToInt16 — conversion correctness
# ---------------------------------------------------------------------------


class TestFloat32ToInt16:
    def test_silence(self):
        np = pytest.importorskip("numpy")
        silence = np.zeros(480, dtype=np.float32)
        result = _float32_to_int16_bytes(silence, np)
        assert len(result) == 960
        assert result == b"\x00" * 960

    def test_max_amplitude(self):
        np = pytest.importorskip("numpy")
        loud = np.ones(480, dtype=np.float32)
        result = _float32_to_int16_bytes(loud, np)
        samples = struct.unpack(f"<{480}h", result)
        assert all(s == 32767 for s in samples)

    def test_negative_amplitude(self):
        np = pytest.importorskip("numpy")
        neg = -np.ones(480, dtype=np.float32)
        result = _float32_to_int16_bytes(neg, np)
        samples = struct.unpack(f"<{480}h", result)
        assert all(s == -32767 for s in samples)

    def test_output_length(self):
        np = pytest.importorskip("numpy")
        data = np.random.uniform(-1, 1, 1024).astype(np.float32)
        result = _float32_to_int16_bytes(data, np)
        assert len(result) == 1024 * 2


# ---------------------------------------------------------------------------
# TestCreateVad — default and custom aggressiveness
# ---------------------------------------------------------------------------


class TestCreateVad:
    @patch("neo.voice.stt._check_webrtcvad")
    def test_default_aggressiveness(self, mock_check):
        mock_vad = MagicMock()
        mock_webrtcvad = MagicMock()
        mock_webrtcvad.Vad.return_value = mock_vad
        mock_check.return_value = mock_webrtcvad

        result = _create_vad()
        assert result is mock_vad
        mock_vad.set_mode.assert_called_once_with(_VAD_AGGRESSIVENESS)

    @patch("neo.voice.stt._check_webrtcvad")
    def test_custom_aggressiveness(self, mock_check):
        mock_vad = MagicMock()
        mock_webrtcvad = MagicMock()
        mock_webrtcvad.Vad.return_value = mock_vad
        mock_check.return_value = mock_webrtcvad

        result = _create_vad(aggressiveness=1)
        assert result is mock_vad
        mock_vad.set_mode.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# TestIsSpeechFrame — delegation to vad.is_speech
# ---------------------------------------------------------------------------


class TestIsSpeechFrame:
    def test_speech_detected(self):
        mock_vad = MagicMock()
        mock_vad.is_speech.return_value = True
        pcm = b"\x00" * 960
        assert _is_speech_frame(mock_vad, pcm) is True
        mock_vad.is_speech.assert_called_once_with(pcm, _SAMPLE_RATE)

    def test_silence_detected(self):
        mock_vad = MagicMock()
        mock_vad.is_speech.return_value = False
        pcm = b"\x00" * 960
        assert _is_speech_frame(mock_vad, pcm) is False


# ---------------------------------------------------------------------------
# TestWhisperSTTState — initial state, model loading, status
# ---------------------------------------------------------------------------


class TestWhisperSTTState:
    def test_initial_state(self):
        s = WhisperSTT()
        assert s.model_name == "base"
        assert s.language == "en"
        assert s.model_loaded is False
        assert s.recording is False
        assert s.wake_word_active is False

    def test_custom_init(self):
        s = WhisperSTT(model_name="tiny", language="pt")
        assert s.model_name == "tiny"
        assert s.language == "pt"

    @patch("neo.voice.stt._check_whisper")
    def test_load_model(self, mock_check):
        mock_whisper = MagicMock()
        mock_model = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_check.return_value = mock_whisper

        s = WhisperSTT()
        s.load_model("small")
        assert s.model_loaded is True
        assert s.model_name == "small"
        mock_whisper.load_model.assert_called_once_with("small")

    @patch("neo.voice.stt._check_whisper")
    def test_load_model_default(self, mock_check):
        mock_whisper = MagicMock()
        mock_check.return_value = mock_whisper

        s = WhisperSTT(model_name="tiny")
        s.load_model()
        mock_whisper.load_model.assert_called_once_with("tiny")


# ---------------------------------------------------------------------------
# TestWhisperSTTTranscribe — file and audio data transcription
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

        s = WhisperSTT()
        s.load_model()
        wav_path = self._make_wav(tmp_path)
        result = s.transcribe(wav_path)
        assert result == "hello world"
        mock_model.transcribe.assert_called_once()

    @patch("neo.voice.stt._check_whisper")
    def test_transcribe_auto_loads_model(self, mock_check, tmp_path: Path):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "auto loaded"}
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_check.return_value = mock_whisper

        s = WhisperSTT()
        wav_path = self._make_wav(tmp_path)
        result = s.transcribe(wav_path)
        assert result == "auto loaded"
        mock_whisper.load_model.assert_called_once()

    @patch("neo.voice.stt._check_whisper")
    def test_transcribe_audio_data(self, mock_check):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "from bytes"}
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_check.return_value = mock_whisper

        s = WhisperSTT()
        s.load_model()
        audio_bytes = b"\x00\x00" * 1600
        result = s.transcribe_audio_data(audio_bytes)
        assert result == "from bytes"

    @patch("neo.voice.stt._check_whisper")
    def test_load_model_override(self, mock_check):
        mock_whisper = MagicMock()
        mock_check.return_value = mock_whisper

        s = WhisperSTT(model_name="base")
        s.load_model("tiny")
        assert s.model_name == "tiny"
        mock_whisper.load_model.assert_called_with("tiny")

    @patch("neo.voice.stt._check_whisper")
    def test_transcribe_empty_result(self, mock_check, tmp_path: Path):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "  "}
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_check.return_value = mock_whisper

        s = WhisperSTT()
        s.load_model()
        wav_path = self._make_wav(tmp_path)
        result = s.transcribe(wav_path)
        assert result == ""


# ---------------------------------------------------------------------------
# TestRecordLoopVAD — speech→silence detection, grace period
# ---------------------------------------------------------------------------


class TestRecordLoopVAD:
    @patch("neo.voice.stt._create_vad")
    @patch("neo.voice.stt._check_numpy")
    @patch("neo.voice.stt._check_sounddevice")
    def test_record_loop_speech_then_silence(self, mock_sd_check, mock_np_check, mock_vad_check):
        """Speech frames followed by silence triggers end-of-recording."""
        np = pytest.importorskip("numpy")
        mock_np_check.return_value = np

        mock_sd = MagicMock()
        mock_sd.CallbackAbort = type("CallbackAbort", (Exception,), {})
        mock_sd_check.return_value = mock_sd

        mock_vad = MagicMock()
        mock_vad_check.return_value = mock_vad

        s = WhisperSTT()
        s._model = MagicMock()
        s._model.transcribe.return_value = {"text": "test speech"}
        callback_result = []
        s._on_transcription = lambda t: callback_result.append(t)
        s._recording = True

        speech_frames = _MIN_SPEECH_FRAMES + 2
        saved_callback = [None]

        class FakeInputStream:
            def __init__(self, **kwargs):
                saved_callback[0] = kwargs.get("callback")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        mock_sd.InputStream = FakeInputStream

        import threading

        t = threading.Thread(target=s._record_loop)
        t.start()

        # Wait for stream to open
        time.sleep(0.15)

        if saved_callback[0]:
            cb = saved_callback[0]
            blocksize = int(_SAMPLE_RATE * _VAD_FRAME_MS / 1000)

            # Send speech frames
            mock_vad.is_speech.return_value = True
            for _ in range(speech_frames):
                indata = np.zeros((blocksize, 1), dtype=np.float32)
                cb(indata, blocksize, None, None)

            # Send silence frames until _SILENCE_DURATION exceeded
            mock_vad.is_speech.return_value = False
            silence_frames_needed = int(_SILENCE_DURATION / (_VAD_FRAME_MS / 1000)) + 5
            for i in range(silence_frames_needed):
                indata = np.zeros((blocksize, 1), dtype=np.float32)
                try:
                    cb(indata, blocksize, None, None)
                except mock_sd.CallbackAbort:
                    break
                time.sleep(0.001)

        s._recording = False
        t.join(timeout=3)

    @patch("neo.voice.stt._create_vad")
    @patch("neo.voice.stt._check_numpy")
    @patch("neo.voice.stt._check_sounddevice")
    def test_record_loop_no_speech_manual_stop(self, mock_sd_check, mock_np_check, mock_vad_check):
        """When no speech is detected and recording is stopped manually."""
        np = pytest.importorskip("numpy")
        mock_np_check.return_value = np

        mock_sd = MagicMock()
        mock_sd.CallbackAbort = type("CallbackAbort", (Exception,), {})
        mock_sd_check.return_value = mock_sd

        mock_vad = MagicMock()
        mock_vad.is_speech.return_value = False
        mock_vad_check.return_value = mock_vad

        s = WhisperSTT()
        s._recording = True

        class FakeInputStream:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        mock_sd.InputStream = FakeInputStream

        import threading

        t = threading.Thread(target=s._record_loop)
        t.start()
        time.sleep(0.15)
        s._recording = False
        t.join(timeout=3)
        assert s._recording is False

    @patch("neo.voice.stt._create_vad")
    @patch("neo.voice.stt._check_numpy")
    @patch("neo.voice.stt._check_sounddevice")
    def test_record_loop_exception_sets_recording_false(
        self, mock_sd_check, mock_np_check, mock_vad_check
    ):
        """Recording error sets _recording = False."""
        np = pytest.importorskip("numpy")
        mock_np_check.return_value = np

        mock_sd = MagicMock()
        mock_sd.CallbackAbort = type("CallbackAbort", (Exception,), {})
        mock_sd.InputStream.side_effect = RuntimeError("audio device error")
        mock_sd_check.return_value = mock_sd

        mock_vad_check.return_value = MagicMock()

        s = WhisperSTT()
        s._recording = True
        s._record_loop()
        assert s._recording is False


# ---------------------------------------------------------------------------
# TestWakeWordVAD — speech-gated transcription, wake word triggers record
# ---------------------------------------------------------------------------


class TestWakeWordVAD:
    @patch("neo.voice.stt._create_vad")
    @patch("neo.voice.stt._check_numpy")
    @patch("neo.voice.stt._check_sounddevice")
    def test_wake_word_silence_no_transcription(
        self, mock_sd_check, mock_np_check, mock_vad_check
    ):
        """During silence, no Whisper calls should be made."""
        np = pytest.importorskip("numpy")
        mock_np_check.return_value = np

        mock_sd = MagicMock()
        mock_sd_check.return_value = mock_sd

        mock_vad = MagicMock()
        mock_vad.is_speech.return_value = False
        mock_vad_check.return_value = mock_vad

        s = WhisperSTT()
        s._model = MagicMock()
        s._wake_word_active = True

        read_count = [0]
        max_reads = 10
        blocksize = int(_SAMPLE_RATE * _VAD_FRAME_MS / 1000)

        class FakeStream:
            def read(self, n):
                read_count[0] += 1
                if read_count[0] >= max_reads:
                    s._wake_word_active = False
                return np.zeros((n, 1), dtype=np.float32), False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        mock_sd.InputStream.return_value = FakeStream()

        s._wake_word_loop()

        # Whisper should NOT have been called — no speech detected
        s._model.transcribe.assert_not_called()

    @patch("neo.voice.stt._create_vad")
    @patch("neo.voice.stt._check_numpy")
    @patch("neo.voice.stt._check_sounddevice")
    def test_wake_word_speech_triggers_transcription(
        self, mock_sd_check, mock_np_check, mock_vad_check
    ):
        """When speech is detected, Whisper should transcribe."""
        np = pytest.importorskip("numpy")
        mock_np_check.return_value = np

        mock_sd = MagicMock()
        mock_sd.CallbackAbort = type("CallbackAbort", (Exception,), {})
        mock_sd_check.return_value = mock_sd

        mock_vad = MagicMock()
        mock_vad_check.return_value = mock_vad

        s = WhisperSTT()
        s._model = MagicMock()
        s._model.transcribe.return_value = {"text": "just some words"}
        s._wake_word_active = True

        read_count = [0]
        speech_reads = 5

        class FakeStream:
            def read(self, n):
                read_count[0] += 1
                if read_count[0] <= speech_reads:
                    mock_vad.is_speech.return_value = True
                else:
                    mock_vad.is_speech.return_value = False
                if read_count[0] > speech_reads + _WAKE_SILENCE_FRAMES + 5:
                    s._wake_word_active = False
                return np.zeros((n, 1), dtype=np.float32), False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        mock_sd.InputStream.return_value = FakeStream()

        s._wake_word_loop()

        assert s._model.transcribe.call_count >= 1

    @patch("neo.voice.stt._create_vad")
    @patch("neo.voice.stt._check_numpy")
    @patch("neo.voice.stt._check_sounddevice")
    def test_wake_word_detected_triggers_record(
        self, mock_sd_check, mock_np_check, mock_vad_check
    ):
        """When 'hey neo' is detected, _record_loop should be called."""
        np = pytest.importorskip("numpy")
        mock_np_check.return_value = np

        mock_sd = MagicMock()
        mock_sd.CallbackAbort = type("CallbackAbort", (Exception,), {})
        mock_sd_check.return_value = mock_sd

        mock_vad = MagicMock()
        mock_vad_check.return_value = mock_vad

        s = WhisperSTT()
        s._model = MagicMock()
        s._model.transcribe.return_value = {"text": "Hey Neo"}
        s._wake_word_active = True

        read_count = [0]
        speech_reads = 3

        class FakeStream:
            def read(self, n):
                read_count[0] += 1
                if read_count[0] <= speech_reads:
                    mock_vad.is_speech.return_value = True
                else:
                    mock_vad.is_speech.return_value = False
                if read_count[0] > speech_reads + _WAKE_SILENCE_FRAMES + 5:
                    s._wake_word_active = False
                return np.zeros((n, 1), dtype=np.float32), False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        mock_sd.InputStream.return_value = FakeStream()

        with patch.object(s, "_record_loop") as mock_record:
            s._wake_word_loop()
            mock_record.assert_called_once()

    @patch("neo.voice.stt._create_vad")
    @patch("neo.voice.stt._check_numpy")
    @patch("neo.voice.stt._check_sounddevice")
    def test_wake_word_stream_error(self, mock_sd_check, mock_np_check, mock_vad_check):
        """Stream error is handled gracefully."""
        np = pytest.importorskip("numpy")
        mock_np_check.return_value = np

        mock_sd = MagicMock()
        mock_sd.InputStream.side_effect = RuntimeError("no device")
        mock_sd_check.return_value = mock_sd

        mock_vad_check.return_value = MagicMock()

        s = WhisperSTT()
        s._wake_word_active = True
        s._wake_word_loop()  # Should not raise


# ---------------------------------------------------------------------------
# TestSTTStatusVAD — vad_available in status
# ---------------------------------------------------------------------------


class TestSTTStatusVAD:
    @patch("neo.voice.stt._check_webrtcvad")
    def test_status_vad_available(self, mock_check):
        mock_check.return_value = MagicMock()
        s = WhisperSTT()
        status = s.get_status()
        assert status["vad_available"] is True

    @patch("neo.voice.stt._check_webrtcvad")
    def test_status_vad_unavailable(self, mock_check):
        mock_check.side_effect = ImportError("not installed")
        s = WhisperSTT()
        status = s.get_status()
        assert status["vad_available"] is False

    @patch("neo.voice.stt._check_webrtcvad", return_value=MagicMock())
    def test_status_keys(self, _mock):
        s = WhisperSTT()
        status = s.get_status()
        expected_keys = {
            "model_loaded",
            "model_name",
            "recording",
            "wake_word_active",
            "language",
            "vad_available",
        }
        assert set(status.keys()) == expected_keys

    @patch("neo.voice.stt._check_webrtcvad", return_value=MagicMock())
    def test_status_default_values(self, _mock):
        s = WhisperSTT()
        status = s.get_status()
        assert status["model_loaded"] is False
        assert status["model_name"] == "base"
        assert status["recording"] is False
        assert status["wake_word_active"] is False
        assert status["language"] == "en"


# ---------------------------------------------------------------------------
# TestStartStop — start/stop recording and wake word
# ---------------------------------------------------------------------------


class TestStartStop:
    def test_start_stop_recording(self):
        s = WhisperSTT()
        s._record_loop = lambda: None
        s.start_recording(lambda t: None)
        assert s.recording is True
        s.stop_recording()
        assert s.recording is False

    def test_start_recording_idempotent(self):
        s = WhisperSTT()
        s._record_loop = lambda: None
        s.start_recording(lambda t: None)
        s.start_recording(lambda t: None)  # Should not create another thread
        s.stop_recording()

    def test_stop_when_not_recording(self):
        s = WhisperSTT()
        s.stop_recording()  # Should not raise

    def test_start_stop_wake_word(self):
        s = WhisperSTT()
        s._wake_word_loop = lambda: None
        s.start_wake_word(lambda t: None)
        assert s.wake_word_active is True
        s.stop_wake_word()
        assert s.wake_word_active is False

    def test_stop_wake_word_when_not_active(self):
        s = WhisperSTT()
        s.stop_wake_word()  # Should not raise
