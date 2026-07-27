from datetime import datetime, timezone

from mediawhisperer.load.render import render_markdown
from mediawhisperer.models import Digest, Note, SourceKind
from mediawhisperer.transform.cluster import cluster_stories


def _note(nid, source, topics, title=None):
    return Note(
        item_id=nid,
        title=title or f"{source} item {nid}",
        source_name=source,
        url=f"https://example.com/{nid}",
        summary="s",
        topics=topics,
    )


def test_clusters_same_story_across_sources():
    notes = [
        _note("1", "Pod A", ["Star Wars", "Galaxy's Edge", "Ride"]),
        _note("2", "Pod B", ["Star Wars", "Galaxy's Edge", "Opening"]),
        _note("3", "Pod C", ["Marvel", "Cruise"]),  # unrelated
    ]
    stories = cluster_stories(notes)
    assert len(stories) == 1
    story = stories[0]
    assert set(story.sources) == {"Pod A", "Pod B"}
    assert "Star Wars" in story.key_topics or "Galaxy's Edge" in story.key_topics


def test_single_source_cluster_is_not_a_story():
    # Two notes share topics but come from the SAME source -> not cross-feed.
    notes = [
        _note("1", "Pod A", ["Star Wars", "Galaxy's Edge"]),
        _note("2", "Pod A", ["Star Wars", "Galaxy's Edge"]),
    ]
    assert cluster_stories(notes) == []


def test_min_shared_threshold_prevents_weak_links():
    # Only one topic in common -> below default min_shared of 2 -> no story.
    notes = [
        _note("1", "Pod A", ["Star Wars", "Ride"]),
        _note("2", "Pod B", ["Star Wars", "Cruise"]),
    ]
    assert cluster_stories(notes) == []
    # Lowering the threshold links them.
    assert len(cluster_stories(notes, min_shared=1)) == 1


def test_stories_sorted_by_source_count():
    notes = [
        _note("1", "A", ["Star Wars", "Edge"]),
        _note("2", "B", ["Star Wars", "Edge"]),
        _note("3", "C", ["Star Wars", "Edge"]),
        _note("4", "D", ["Marvel", "Cruise"]),
        _note("5", "E", ["Marvel", "Cruise"]),
    ]
    stories = cluster_stories(notes)
    assert len(stories) == 2
    # The 3-source Star Wars story ranks ahead of the 2-source Marvel one.
    assert len(stories[0].sources) == 3


def test_markdown_renders_stories_section():
    notes = [
        _note("1", "Pod A", ["Star Wars", "Galaxy's Edge"], title="Edge at Five"),
        _note("2", "Pod B", ["Star Wars", "Galaxy's Edge"], title="Return to Batuu"),
    ]
    md = render_markdown(Digest(generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc), notes=notes))
    assert "Top stories across your feeds" in md
    assert "Covered by 2 sources: Pod A, Pod B" in md
    assert "Edge at Five" in md


def test_no_stories_section_when_nothing_clusters():
    notes = [
        _note("1", "Pod A", ["Star Wars"]),
        _note("2", "Pod B", ["Marvel"]),
    ]
    md = render_markdown(Digest(generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc), notes=notes))
    assert "Top stories across your feeds" not in md
