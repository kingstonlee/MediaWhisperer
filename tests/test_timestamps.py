from mediawhisperer.load.render import deep_link, render_html, render_markdown
from mediawhisperer.models import Digest, Note, SourceKind, Transcript
from mediawhisperer.transform.captions import parse_vtt_cues
from mediawhisperer.transform.summarize import ExtractiveSummarizer
from mediawhisperer.transform.timing import format_timestamp, locate_time

VTT = """WEBVTT

00:00:01.000 --> 00:00:03.000
The new roller coaster opened this weekend.

00:00:03.000 --> 00:00:05.000
Guests waited three hours to ride the new roller coaster.

01:02:03.000 --> 01:02:06.000
Officials expect record attendance all summer.
"""


def test_parse_vtt_cues_captures_start_times():
    cues = parse_vtt_cues(VTT)
    assert cues[0]["start"] == 1.0
    assert cues[1]["start"] == 3.0
    assert cues[2]["start"] == 3723.0  # 1h 2m 3s
    assert "roller coaster" in cues[0]["text"].lower()


def test_format_timestamp():
    assert format_timestamp(5) == "0:05"
    assert format_timestamp(75) == "1:15"
    assert format_timestamp(3723) == "1:02:03"


def test_locate_time_finds_segment():
    segments = [{"start": 1.0, "text": "The new roller coaster opened this weekend."},
                {"start": 5.0, "text": "Officials expect record attendance all summer."}]
    assert locate_time(segments, "Officials expect record attendance") == 5.0
    assert locate_time(segments, "The new roller coaster") == 1.0


def test_locate_time_no_segments_returns_none():
    assert locate_time([], "anything") is None


def test_extractive_summary_attaches_timestamps():
    text = (
        "The new roller coaster opened this weekend. "
        "Guests waited over three hours to ride the new roller coaster. "
        "The coaster features three inversions and hits sixty miles per hour. "
        "A spokesperson said the coaster is the most advanced attraction ever built. "
        "Officials expect the new roller coaster to draw record attendance all summer."
    )
    # Segments give each sentence a start time.
    segments = [
        {"start": float(i * 10), "text": s.strip() + "."}
        for i, s in enumerate(text.rstrip(".").split(". "))
    ]
    transcript = Transcript(
        item_id="x", title="Coaster", source_name="Parks", text=text, segments=segments
    )
    note = ExtractiveSummarizer().summarize(transcript, summary_sentences=2, highlights=2)
    assert note.highlights
    assert len(note.highlight_times) == len(note.highlights)
    # At least one highlight resolved to a real timestamp.
    assert any(t is not None for t in note.highlight_times)


def test_youtube_deep_link_built():
    note = Note(
        item_id="1", title="V", source_name="Chan", url="https://youtube.com/watch?v=abc",
        summary="s", kind=SourceKind.YOUTUBE,
    )
    assert deep_link(note, 92) == "https://youtube.com/watch?v=abc&t=92s"


def test_podcast_has_no_deep_link():
    note = Note(item_id="1", title="E", source_name="Pod", url="https://ex.com/ep",
                summary="s", kind=SourceKind.PODCAST)
    assert deep_link(note, 92) is None


def _digest_with_times() -> Digest:
    from datetime import datetime, timezone

    yt = Note(
        item_id="1", title="A Video", source_name="Channel",
        url="https://youtube.com/watch?v=abc", summary="Summary.",
        highlights=["A big announcement.", "A second point."],
        highlight_times=[92.0, None], kind=SourceKind.YOUTUBE,
    )
    pod = Note(
        item_id="2", title="An Episode", source_name="Podcast",
        url="https://ex.com/ep", summary="Summary.",
        highlights=["Something notable."], highlight_times=[3723.0],
        kind=SourceKind.PODCAST,
    )
    return Digest(generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc), notes=[yt, pod])


def test_markdown_renders_youtube_link_and_podcast_label():
    md = render_markdown(_digest_with_times())
    assert "[[1:32](https://youtube.com/watch?v=abc&t=92s)]" in md  # clickable jump
    assert "_[1:02:03]_" in md  # podcast: plain label, no link


def test_html_renders_timestamps():
    html = render_html(_digest_with_times())
    assert 'class="ts"' in html
    assert "t=92s" in html
