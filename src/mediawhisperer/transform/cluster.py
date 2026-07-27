"""Group notes that cover the same story across different feeds.

The point of a digest is signal over noise: when five shows all cover "new
Star Wars land announced" in the same week, you want to see that *once*, with
the sources that thought it mattered -- not five near-identical entries.

We cluster on the topic tags each note already carries (no embeddings, no
network). Two notes are linked when they share enough topics; linked notes form
connected components via union-find. A component that spans more than one source
is a cross-feed "story".

Pure function -- deterministic and unit testable.
"""

from __future__ import annotations

from collections import Counter

from ..models import Note, Story


def cluster_stories(
    notes: list[Note],
    min_shared: int = 2,
    min_sources: int = 2,
) -> list[Story]:
    """Return cross-feed stories, most-covered first.

    A story is a set of notes from at least ``min_sources`` distinct sources,
    linked by sharing at least ``min_shared`` topics (case-insensitive).
    """
    topic_sets = [{t.lower() for t in note.topics} for note in notes]

    parent = list(range(len(notes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            if len(topic_sets[i] & topic_sets[j]) >= min_shared:
                union(i, j)

    components: dict[int, list[int]] = {}
    for i in range(len(notes)):
        components.setdefault(find(i), []).append(i)

    stories: list[Story] = []
    for members_idx in components.values():
        members = [notes[i] for i in members_idx]
        distinct_sources = {n.source_name for n in members}
        if len(distinct_sources) < min_sources:
            continue  # single-feed cluster -- not a cross-feed story

        # Key topics: those shared by the most members, most common first.
        topic_counts: Counter[str] = Counter()
        for i in members_idx:
            topic_counts.update(topic_sets[i])
        key = [t for t, c in topic_counts.most_common() if c >= 2][:3]

        # Order members newest-first for display.
        members.sort(key=lambda n: (n.published is not None, n.published), reverse=True)
        stories.append(Story(key_topics=[_titlecase(t) for t in key], members=members))

    # Most-covered stories (by source count, then size) first.
    stories.sort(key=lambda s: (len(s.sources), len(s.members)), reverse=True)
    return stories


def _titlecase(phrase: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in phrase.split())
