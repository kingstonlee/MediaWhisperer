from pathlib import Path

import pytest

from mediawhisperer.extract.opml import parse_opml
from mediawhisperer.models import SourceKind

FIXTURE = Path(__file__).parent / "fixtures" / "subscriptions.opml"


def test_parses_nested_and_flat_outlines():
    sources = parse_opml(FIXTURE.read_text(encoding="utf-8"))
    urls = [s.url for s in sources]
    assert "https://example.com/parks/feed.xml" in urls
    assert "https://example.com/starwars/feed.xml" in urls
    assert "https://example.com/marvel/feed.xml" in urls


def test_all_imports_are_podcast_kind():
    sources = parse_opml(FIXTURE.read_text(encoding="utf-8"))
    assert all(s.kind is SourceKind.PODCAST for s in sources)


def test_duplicate_urls_are_dropped():
    sources = parse_opml(FIXTURE.read_text(encoding="utf-8"))
    # parks/feed.xml appears twice in the fixture; keep one.
    assert [s.url for s in sources].count("https://example.com/parks/feed.xml") == 1


def test_outline_without_url_is_ignored():
    sources = parse_opml(FIXTURE.read_text(encoding="utf-8"))
    assert all("no feed" not in s.name.lower() for s in sources)


def test_prefers_title_then_text_for_name():
    sources = {s.url: s for s in parse_opml(FIXTURE.read_text(encoding="utf-8"))}
    # Has both title and text -> title wins.
    assert sources["https://example.com/parks/feed.xml"].name == "Parks Podcast"
    # Only text -> text used.
    assert sources["https://example.com/marvel/feed.xml"].name == "Marvel Weekly"


def test_invalid_xml_raises_value_error():
    with pytest.raises(ValueError):
        parse_opml("this is not xml <<<")
