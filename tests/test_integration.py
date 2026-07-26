"""Heavier integration tests.

The environment's egress policy blocks third-party content hosts, so these
tests can't hit a real podcast CDN or YouTube. Instead they prove the same
machinery two ways:

* the **download path** runs against a real HTTP server on localhost, so
  ``feedparser`` discovery and the ``requests`` download are genuinely
  exercised over the wire (not mocked); and
* the **Whisper** and **captions** transcribers run against injected backends,
  proving our integration wiring (result mapping, subtitle discovery + parsing)
  without the multi-gigabyte model or a network fetch.
"""

from __future__ import annotations

import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mediawhisperer.extract.podcast import PodcastExtractor
from mediawhisperer.models import MediaItem, Source, SourceKind
from mediawhisperer.transform.transcribe import (
    CaptionsTranscriber,
    WhisperTranscriber,
    get_transcriber,
)

AUDIO_BYTES = b"ID3" + b"\x00" * 512  # stand-in for a real episode's audio


@pytest.fixture()
def local_server(tmp_path):
    """Serve a temp dir over HTTP on localhost, yielding the base URL."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path
    finally:
        server.shutdown()
        server.server_close()


def test_discover_and_download_over_real_http(local_server, tmp_path):
    base_url, root = local_server
    (root / "ep.mp3").write_bytes(AUDIO_BYTES)
    (root / "feed.xml").write_text(
        f"""<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Local</title>
          <item>
            <title>Episode One</title>
            <link>{base_url}/ep-1</link>
            <guid>{base_url}/ep-1</guid>
            <pubDate>Mon, 02 Jun 2025 09:00:00 +0000</pubDate>
            <enclosure url="{base_url}/ep.mp3" type="audio/mpeg"/>
          </item>
        </channel></rss>""",
        encoding="utf-8",
    )

    source = Source(
        name="Local",
        kind=SourceKind.PODCAST,
        url=f"{base_url}/feed.xml",
        lookback_days=100_000,
    )

    # Real feed parse over HTTP.
    items = PodcastExtractor().discover(source)
    assert len(items) == 1
    assert items[0].media_url == f"{base_url}/ep.mp3"

    # Real download over HTTP.
    dest = PodcastExtractor().fetch(items[0], tmp_path / "downloads")
    assert dest.exists()
    assert dest.read_bytes() == AUDIO_BYTES
    assert items[0].local_path == str(dest)


def test_whisper_backend_maps_model_output(tmp_path):
    """Prove our Whisper wiring without downloading the model."""

    class FakeModel:
        def transcribe(self, path):
            assert Path(path).exists()
            return {"text": "  This is the spoken transcript.  "}

    audio = tmp_path / "clip.wav"
    audio.write_bytes(AUDIO_BYTES)

    transcriber = WhisperTranscriber()
    transcriber._model = FakeModel()  # inject, bypassing whisper.load_model()

    item = MediaItem(
        source_name="Pod",
        kind=SourceKind.PODCAST,
        title="Ep",
        url="https://example.com/ep",
        local_path=str(audio),
    )
    transcript = transcriber.transcribe(item)
    assert transcript.text == "This is the spoken transcript."
    assert transcript.provenance == "whisper"


def test_whisper_requires_downloaded_media():
    transcriber = WhisperTranscriber()
    transcriber._model = object()
    item = MediaItem(source_name="P", kind=SourceKind.PODCAST, title="E", url="u")
    with pytest.raises(ValueError, match="no downloaded media"):
        transcriber.transcribe(item)


def test_captions_backend_fetches_and_parses(tmp_path, monkeypatch):
    """Inject a fake yt-dlp that drops a real VTT file, proving fetch + parse."""

    vtt = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\n"
        "welcome to the show\n\n"
        "00:00:02.000 --> 00:00:04.000\n"
        "today we tour the new land\n"
    )

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            # Mimic yt-dlp writing a subtitle file next to the outtmpl.
            out_dir = Path(self.opts["outtmpl"]).parent
            (out_dir / "video.en.vtt").write_text(vtt, encoding="utf-8")
            return {"id": "video"}

    fake_module = type(sys)("yt_dlp")
    fake_module.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)

    item = MediaItem(
        source_name="Channel",
        kind=SourceKind.YOUTUBE,
        title="A Video",
        url="https://youtube.com/watch?v=abc",
        media_url="https://youtube.com/watch?v=abc",
    )
    transcript = CaptionsTranscriber().transcribe(item)
    assert transcript.provenance == "captions"
    assert "welcome to the show" in transcript.text
    assert "today we tour the new land" in transcript.text
    assert "-->" not in transcript.text  # timing stripped


def test_captions_falls_back_to_feed_when_no_subs(tmp_path, monkeypatch):
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            return {"id": "video"}  # writes no .vtt

    fake_module = type(sys)("yt_dlp")
    fake_module.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)

    item = MediaItem(
        source_name="Channel",
        kind=SourceKind.YOUTUBE,
        title="Uncaptioned",
        url="https://youtube.com/watch?v=xyz",
        summary_hint="The video description saves the day.",
    )
    transcript = CaptionsTranscriber().transcribe(item)
    assert transcript.provenance == "feed"
    assert "description saves the day" in transcript.text


def test_transcriber_registry_exposes_all_backends():
    for name in ("feed", "captions", "whisper"):
        assert get_transcriber(name) is not None
