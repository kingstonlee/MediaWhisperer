import pytest

from mediawhisperer.load.tts import get_voice


def test_script_backend_writes_text(tmp_path):
    voice = get_voice("script")
    dest = tmp_path / "out.txt"
    voice.synthesize("Hello there.", dest)
    assert dest.read_text(encoding="utf-8") == "Hello there."
    assert voice.suffix == ".txt"


def test_elevenlabs_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    voice = get_voice("elevenlabs")
    with pytest.raises(RuntimeError, match="API key"):
        voice.synthesize("Hello.", tmp_path / "out.mp3")


def test_elevenlabs_posts_and_writes_audio(tmp_path, monkeypatch):
    captured = {}

    class FakeResponse:
        content = b"ID3fake-audio-bytes"

        def raise_for_status(self):
            captured["raised"] = True

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)

    voice = get_voice("elevenlabs", api_key="secret", voice_id="VOICE123")
    dest = tmp_path / "digest.mp3"
    result = voice.synthesize("Here is your digest.", dest)

    assert result == dest
    assert dest.read_bytes() == b"ID3fake-audio-bytes"
    # Correct endpoint, auth header, and payload were sent.
    assert "VOICE123" in captured["url"]
    assert captured["headers"]["xi-api-key"] == "secret"
    assert captured["json"]["text"] == "Here is your digest."
    assert voice.suffix == ".mp3"


def test_elevenlabs_reads_key_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "env-key")

    class FakeResponse:
        content = b"audio"

        def raise_for_status(self):
            pass

    def fake_post(url, headers=None, json=None, timeout=None):
        assert headers["xi-api-key"] == "env-key"
        return FakeResponse()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)
    get_voice("elevenlabs").synthesize("Hi.", tmp_path / "o.mp3")


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="Unknown tts backend"):
        get_voice("does-not-exist")
