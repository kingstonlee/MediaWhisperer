from datetime import datetime, timezone

from mediawhisperer.load.render import digest_themes, render_html, render_markdown, render_script
from mediawhisperer.models import Digest, Note


def _digest() -> Digest:
    notes = [
        Note(
            item_id="1",
            title="Galaxy's Edge Turns Five",
            source_name="Parks Pod",
            url="https://example.com/1",
            summary="The Star Wars land marked five years.",
            highlights=["Rise of the Resistance improved."],
            topics=["Star Wars", "Galaxy's Edge"],
            published=datetime(2025, 6, 2, tzinfo=timezone.utc),
        ),
        Note(
            item_id="2",
            title="A Star Wars Show",
            source_name="Video Channel",
            url="https://example.com/2",
            summary="More Star Wars news today.",
            highlights=[],
            topics=["Star Wars", "Mandalorian"],
            published=datetime(2025, 6, 3, tzinfo=timezone.utc),
        ),
    ]
    return Digest(generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc), notes=notes)


def test_themes_surface_cross_feed_topic():
    themes = digest_themes(_digest())
    assert themes[0] == "Star Wars"  # appears in both items


def test_markdown_includes_themes_and_topics():
    md = render_markdown(_digest())
    assert "Today's themes:" in md
    assert "Star Wars" in md
    assert "_Topics:" in md


def test_script_is_plain_and_mentions_themes():
    script = render_script(_digest())
    assert "Today's big themes:" in script
    assert "](" not in script  # no markdown leaks into narration


def test_html_is_self_contained_and_escaped():
    html = render_html(_digest())
    assert html.startswith("<!doctype html>")
    assert "<style>" in html
    # No external asset references.
    assert "http://" not in html.replace("https://example.com", "")
    assert "Star Wars" in html


def test_html_escapes_special_characters():
    digest = _digest()
    digest.notes[0].title = "Tom & Jerry <parks>"
    html = render_html(digest)
    assert "Tom &amp; Jerry &lt;parks&gt;" in html
