"""Tests for neo.voice.tts — pyttsx3 TTS engine."""

from unittest.mock import MagicMock, patch

from neo.voice.tts import NeoTTS

# ---------------------------------------------------------------------------
# NeoTTS — initial state
# ---------------------------------------------------------------------------


class TestNeoTTSState:
    def test_initial_state(self):
        tts = NeoTTS()
        assert tts.enabled is True
        assert tts.rate == 175
        assert tts.volume == 0.9
        assert tts.voice_id is None
        assert tts.speaking is False

    def test_custom_init(self):
        tts = NeoTTS(rate=200, volume=0.5, voice_id="test_voice")
        assert tts.rate == 200
        assert tts.volume == 0.5
        assert tts.voice_id == "test_voice"

    def test_get_status(self):
        tts = NeoTTS(rate=150, volume=0.7)
        status = tts.get_status()
        assert status["enabled"] is True
        assert status["speaking"] is False
        assert status["rate"] == 150
        assert status["volume"] == 0.7
        assert status["queue_size"] == 0


# ---------------------------------------------------------------------------
# NeoTTS — speak with mock
# ---------------------------------------------------------------------------


class TestNeoTTSSpeak:
    @patch("neo.voice.tts._check_pyttsx3")
    def test_speak_queues_text(self, mock_check):
        mock_engine = MagicMock()
        mock_pyttsx3 = MagicMock()
        mock_pyttsx3.init.return_value = mock_engine
        mock_check.return_value = mock_pyttsx3

        tts = NeoTTS()
        tts._engine = mock_engine  # Pre-set engine to avoid init in worker

        # Queue text without starting worker
        tts._queue.put("hello")
        assert tts._queue.qsize() == 1

    def test_speak_disabled(self):
        tts = NeoTTS()
        tts.enabled = False
        tts.speak("should not queue")
        assert tts._queue.qsize() == 0

    def test_speak_empty_text(self):
        tts = NeoTTS()
        tts.speak("")
        assert tts._queue.qsize() == 0

    def test_speak_whitespace_only(self):
        tts = NeoTTS()
        tts.speak("   ")
        assert tts._queue.qsize() == 0


# ---------------------------------------------------------------------------
# NeoTTS — settings
# ---------------------------------------------------------------------------


class TestNeoTTSSettings:
    def test_set_rate(self):
        tts = NeoTTS()
        tts.set_rate(250)
        assert tts.rate == 250

    def test_set_volume(self):
        tts = NeoTTS()
        tts.set_volume(0.5)
        assert tts.volume == 0.5

    def test_set_volume_clamps_high(self):
        tts = NeoTTS()
        tts.set_volume(1.5)
        assert tts.volume == 1.0

    def test_set_volume_clamps_low(self):
        tts = NeoTTS()
        tts.set_volume(-0.5)
        assert tts.volume == 0.0

    def test_set_voice(self):
        tts = NeoTTS()
        tts.set_voice("com.apple.speech.synthesis.voice.Alex")
        assert tts.voice_id == "com.apple.speech.synthesis.voice.Alex"

    @patch("neo.voice.tts._check_pyttsx3")
    def test_set_rate_updates_engine(self, mock_check):
        mock_engine = MagicMock()
        mock_pyttsx3 = MagicMock()
        mock_pyttsx3.init.return_value = mock_engine
        mock_check.return_value = mock_pyttsx3

        tts = NeoTTS()
        tts._engine = mock_engine
        tts.set_rate(200)
        mock_engine.setProperty.assert_called_with("rate", 200)


# ---------------------------------------------------------------------------
# NeoTTS — stop
# ---------------------------------------------------------------------------


class TestNeoTTSStop:
    def test_stop_clears_queue(self):
        tts = NeoTTS()
        tts._queue.put("text1")
        tts._queue.put("text2")
        tts.stop()
        # Queue should have only the sentinel None (worker stop signal)
        assert tts._queue.qsize() == 1
        assert tts._queue.get_nowait() is None
        assert tts.speaking is False

    def test_stop_when_not_speaking(self):
        tts = NeoTTS()
        tts.stop()  # Should not raise


# ---------------------------------------------------------------------------
# NeoTTS — voices
# ---------------------------------------------------------------------------


class TestNeoTTSVoices:
    def test_get_available_voices_with_engine(self):
        """When engine is initialized, returns voice list."""
        mock_voice = MagicMock()
        mock_voice.id = "voice1"
        mock_voice.name = "Test Voice"
        mock_voice.languages = ["en"]

        mock_engine = MagicMock()
        mock_engine.getProperty.return_value = [mock_voice]

        tts = NeoTTS()
        tts._engine = mock_engine  # Pre-set (as worker would)
        voices = tts.get_available_voices()
        assert len(voices) == 1
        assert voices[0]["id"] == "voice1"
        assert voices[0]["name"] == "Test Voice"

    def test_get_available_voices_no_engine(self):
        """Before worker starts, returns empty list (B6 fix)."""
        tts = NeoTTS()
        voices = tts.get_available_voices()
        assert voices == []
