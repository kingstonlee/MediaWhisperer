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
