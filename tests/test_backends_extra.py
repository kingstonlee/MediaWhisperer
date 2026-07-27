"""Tests for the faster-whisper transcriber and Piper voice backend."""

from pathlib import Path

import pytest

from mediawhisperer.load.tts import get_voice
from mediawhisperer.models import MediaItem, SourceKind
from mediawhisperer.transform.transcribe import (
    FasterWhisperTranscriber,
    get_transcriber,
)


# --- faster-whisper ---------------------------------------------------------

def test_faster_whisper_maps_segments(tmp_path):
    class FakeSegment:
        def __init__(self, text, start=0.0):
            self.text = text
            self.start = start

    class FakeModel:
        def transcribe(self, path):
            assert Path(path).exists()
            return ([FakeSegment(" Hello there. ", 0.0), FakeSegment(" Second part. ", 4.2)], {"language": "en"})

    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF....")

    t = FasterWhisperTranscriber()
    t._model = FakeModel()  # inject, bypassing the real model load

    item = MediaItem(
        source_name="Pod",
        kind=SourceKind.PODCAST,
        title="Ep",
        url="https://example.com/ep",
        local_path=str(audio),
    )
    transcript = t.transcribe(item)
    assert transcript.text == "Hello there. Second part."
    assert transcript.provenance == "faster-whisper"


def test_faster_whisper_requires_media():
    t = FasterWhisperTranscriber()
    t._model = object()
    item = MediaItem(source_name="P", kind=SourceKind.PODCAST, title="E", url="u")
    with pytest.raises(ValueError, match="no downloaded media"):
        t.transcribe(item)


def test_faster_whisper_registered():
    assert isinstance(get_transcriber("faster-whisper"), FasterWhisperTranscriber)


# --- Piper ------------------------------------------------------------------

def test_piper_requires_model(tmp_path):
    voice = get_voice("piper")
    with pytest.raises(RuntimeError, match="voice model"):
        voice.synthesize("Hello.", tmp_path / "out.wav")


def test_piper_missing_binary(tmp_path):
    voice = get_voice("piper", model=str(tmp_path / "voice.onnx"), piper_bin="definitely-not-a-real-bin")
    with pytest.raises(RuntimeError, match="not found"):
        voice.synthesize("Hello.", tmp_path / "out.wav")


def test_piper_invokes_binary(tmp_path, monkeypatch):
    captured = {}

    def fake_which(name):
        return "/usr/bin/piper"

    def fake_run(cmd, input=None, check=None):
        captured["cmd"] = cmd
        captured["input"] = input
        # Simulate piper writing the output file.
        out_index = cmd.index("--output_file") + 1
        Path(cmd[out_index]).write_bytes(b"RIFFfake-wav")

        class R:
            returncode = 0

        return R()

    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    model = tmp_path / "voice.onnx"
    model.write_bytes(b"onnx")
    dest = tmp_path / "digest.wav"

    voice = get_voice("piper", model=str(model))
    result = voice.synthesize("Here is your digest.", dest)

    assert result == dest
    assert dest.read_bytes() == b"RIFFfake-wav"
    assert "--model" in captured["cmd"]
    assert captured["input"] == b"Here is your digest."
    assert voice.suffix == ".wav"
