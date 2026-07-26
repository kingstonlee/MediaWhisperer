from pathlib import Path

from mediawhisperer.extract.podcast import PodcastExtractor
from mediawhisperer.models import Source, SourceKind

FIXTURE = Path(__file__).parent / "fixtures" / "sample_feed.xml"


def _source(**overrides) -> Source:
    params = dict(
        name="Test Parks Podcast",
        kind=SourceKind.PODCAST,
        url=FIXTURE.as_uri(),
        lookback_days=100_000,  # effectively disable date filtering for the fixture
        max_items=10,
    )
    params.update(overrides)
    return Source(**params)


def test_discover_parses_items_with_enclosures():
    items = PodcastExtractor().discover(_source())
    # Two items have audio; the third (no enclosure) must be skipped.
    assert len(items) == 2
    titles = {it.title for it in items}
    assert "Galaxy's Edge Turns Five" in titles
    assert "No Audio Here" not in titles


def test_discover_sorts_newest_first_and_respects_max_items():
    items = PodcastExtractor().discover(_source(max_items=1))
    assert len(items) == 1
    # Newest of the two enclosure items is the June 9 episode.
    assert items[0].title == "Marvel Day at Sea Returns"


def test_item_captures_media_url_and_duration():
    items = PodcastExtractor().discover(_source())
    by_title = {it.title: it for it in items}
    ep = by_title["Galaxy's Edge Turns Five"]
    assert ep.media_url == "https://example.com/media/ep-101.mp3"
    assert ep.duration_seconds == 32 * 60 + 10
    assert ep.summary_hint  # HTML stripped, non-empty


def test_item_id_is_stable_and_url_derived():
    items = PodcastExtractor().discover(_source())
    first = items[0]
    # Same URL -> same id across constructions.
    from mediawhisperer.models import MediaItem

    twin = MediaItem(
        source_name="x", kind=SourceKind.PODCAST, title="y", url=first.url
    )
    assert twin.id == first.id


def test_lookback_filters_old_items():
    # A 1-day lookback against a 2025 fixture should drop everything.
    items = PodcastExtractor().discover(_source(lookback_days=1))
    assert items == []
