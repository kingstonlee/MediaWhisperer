"""Voice backends that turn a narration script into an audio podcast.

Same registry pattern as the other swappable stages. The default ``script``
backend writes the narration to a ``.txt`` file only -- it produces no audio but
guarantees the pipeline finishes with a usable deliverable and no external
dependency. Real audio comes from opt-in backends:

* ``pyttsx3`` -- fully offline, uses the OS speech engine, writes a real wav.

A cloud voice backend (e.g. a hosted neural TTS) can register here later behind
an API key without changing any caller.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

_REGISTRY: dict[str, type["VoiceBackend"]] = {}


def register(name: str):
    def wrapper(cls: type["VoiceBackend"]) -> type["VoiceBackend"]:
        _REGISTRY[name] = cls
        return cls

    return wrapper


def get_voice(name: str, **options) -> "VoiceBackend":
    if name not in _REGISTRY:
        valid = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown tts backend {name!r}. Available: {valid}")
    return _REGISTRY[name](**options)


class VoiceBackend(ABC):
    #: File extension of what this backend emits.
    suffix = ".txt"

    def __init__(self, **options) -> None:
        self.options = options

    @abstractmethod
    def synthesize(self, script: str, dest: Path) -> Path:
        """Write the rendered output for ``script`` to ``dest`` and return it."""


@register("script")
class ScriptOnlyBackend(VoiceBackend):
    """No audio -- just persists the narration script for review or manual TTS."""

    suffix = ".txt"

    def synthesize(self, script: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(script, encoding="utf-8")
        return dest


@register("elevenlabs")
class ElevenLabsBackend(VoiceBackend):
    """Neural cloud text-to-speech via the ElevenLabs API.

    Produces a natural-sounding MP3. Needs an API key, read from
    ``options["api_key"]`` or the ``ELEVENLABS_API_KEY`` environment variable
    (the env var is preferred so keys never live in the config file).

    Options:
        api_key:  overrides ELEVENLABS_API_KEY.
        voice_id: ElevenLabs voice id (or ELEVENLABS_VOICE_ID env var).
        model_id: TTS model (default "eleven_multilingual_v2").
    """

    suffix = ".mp3"
    _ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    def synthesize(self, script: str, dest: Path) -> Path:
        import requests

        api_key = self.options.get("api_key") or os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ElevenLabs needs an API key. Set ELEVENLABS_API_KEY or put "
                "api_key under backends.options in your config."
            )
        voice_id = (
            self.options.get("voice_id")
            or os.environ.get("ELEVENLABS_VOICE_ID")
            or "21m00Tcm4TlvDq8ikWAM"  # a default stock voice
        )
        model_id = self.options.get("model_id", "eleven_multilingual_v2")

        dest.parent.mkdir(parents=True, exist_ok=True)
        response = requests.post(
            self._ENDPOINT.format(voice_id=voice_id),
            headers={
                "xi-api-key": api_key,
                "accept": "audio/mpeg",
                "content-type": "application/json",
            },
            json={
                "text": script,
                "model_id": model_id,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=120,
        )
        response.raise_for_status()
        dest.write_bytes(response.content)
        return dest


@register("piper")
class PiperBackend(VoiceBackend):
    """Offline neural text-to-speech via Piper.

    Piper produces natural-sounding speech entirely locally and for free -- a
    big step up from the robotic OS voices of pyttsx3, with no API key. It needs
    a downloaded voice model (a ``.onnx`` file plus its ``.onnx.json`` config);
    grab one from the Piper voices catalog and point ``model`` at it.

    Options:
        model:      path to the voice's ``.onnx`` file (required).
        piper_bin:  the piper executable (default "piper").
    """

    suffix = ".wav"

    def synthesize(self, script: str, dest: Path) -> Path:
        import shutil
        import subprocess

        model = self.options.get("model")
        if not model:
            raise RuntimeError(
                "Piper needs a voice model. Set 'model' under backends.options "
                "to a downloaded .onnx voice file."
            )
        piper_bin = self.options.get("piper_bin", "piper")
        if shutil.which(piper_bin) is None and not Path(piper_bin).exists():
            raise RuntimeError(
                f"Piper executable {piper_bin!r} not found. "
                "Install it with: pip install 'mediawhisperer[piper]'"
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [piper_bin, "--model", str(model), "--output_file", str(dest)],
            input=script.encode("utf-8"),
            check=True,
        )
        return dest


@register("pyttsx3")
class Pyttsx3Backend(VoiceBackend):
    """Offline OS-level text-to-speech producing a real audio file."""

    suffix = ".wav"

    def synthesize(self, script: str, dest: Path) -> Path:
        try:
            import pyttsx3
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "pyttsx3 is required for the pyttsx3 tts backend. "
                "Install it with: pip install 'mediawhisperer[voice]'"
            ) from exc

        dest.parent.mkdir(parents=True, exist_ok=True)
        engine = pyttsx3.init()
        if "rate" in self.options:
            engine.setProperty("rate", self.options["rate"])
        engine.save_to_file(script, str(dest))
        engine.runAndWait()
        return dest
