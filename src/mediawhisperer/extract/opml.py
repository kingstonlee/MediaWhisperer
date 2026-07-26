"""Import podcast subscriptions from an OPML file.

Every podcast app (Apple Podcasts, Overcast, Pocket Casts, ...) can export your
subscriptions as OPML -- an XML format where each feed is an ``<outline>`` with
an ``xmlUrl`` attribute. This lets a user bring their entire listening list into
MediaWhisperer in one step instead of hand-copying feed URLs.

Parsing uses the stdlib XML parser (no dependency) and is a pure function, so
the awkward real-world shapes (nested category folders, missing titles) are
easy to unit test.
"""

from __future__ import annotations

from xml.etree import ElementTree

from ..models import Source, SourceKind


def parse_opml(content: str) -> list[Source]:
    """Return a podcast :class:`Source` for every feed outline in the OPML.

    Outlines are often nested inside category folders; we walk the tree and pick
    up any node carrying an ``xmlUrl``, regardless of depth.
    """
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ValueError(f"Not a valid OPML/XML document: {exc}") from exc

    sources: list[Source] = []
    seen_urls: set[str] = set()

    for outline in root.iter("outline"):
        url = outline.get("xmlUrl")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        name = (
            outline.get("title")
            or outline.get("text")
            or _fallback_name(url)
        ).strip()
        sources.append(Source(name=name, kind=SourceKind.PODCAST, url=url))

    return sources


def _fallback_name(url: str) -> str:
    from urllib.parse import urlparse

    host = urlparse(url).netloc
    return host or "Imported feed"
