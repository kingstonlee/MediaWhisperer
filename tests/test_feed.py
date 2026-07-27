from datetime import datetime, timezone
from xml.etree import ElementTree

from mediawhisperer.load.feed import FeedMeta, build_rss, mime_for, update_feed

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def _meta(**kw):
    base = dict(title="My Briefing", description="Daily digest", author="Me",
                base_url="https://host.example.com/digests", max_episodes=3)
    base.update(kw)
    return FeedMeta(**base)


def _episode(name, ts):
    return {
        "guid": name, "title": f"Digest {name}", "description": "d",
        "filename": name, "length": 123, "type": "audio/wav",
        "pubDate": "Mon, 02 Jun 2025 09:00:00 +0000", "_sort": ts,
    }


def test_build_rss_is_valid_xml_with_channel_and_items():
    xml = build_rss(_meta(), [_episode("digest-2025-06-02.wav", 1.0)])
    root = ElementTree.fromstring(xml)
    assert root.tag == "rss"
    channel = root.find("channel")
    assert channel.find("title").text == "My Briefing"
    assert channel.find(f"{ITUNES}author").text == "Me"
    item = channel.find("item")
    enclosure = item.find("enclosure")
    assert enclosure.get("url") == "https://host.example.com/digests/digest-2025-06-02.wav"
    assert enclosure.get("type") == "audio/wav"


def test_build_rss_escapes_special_chars():
    ep = _episode("a.wav", 1.0)
    ep["title"] = "Tom & Jerry <live>"
    xml = build_rss(_meta(), [ep])
    # Parses cleanly (escaping worked) and round-trips the text.
    root = ElementTree.fromstring(xml)
    assert root.find("channel/item/title").text == "Tom & Jerry <live>"


def test_mime_for():
    assert mime_for("x.mp3") == "audio/mpeg"
    assert mime_for("x.wav") == "audio/wav"
    assert mime_for("x.bin") == "application/octet-stream"


def test_update_feed_creates_files(tmp_path):
    audio = tmp_path / "digest-2025-06-02.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 100)

    feed_dir = tmp_path / "podcast"
    feed_path = update_feed(
        feed_dir, _meta(), audio, "Digest 1", "desc",
        datetime(2025, 6, 2, tzinfo=timezone.utc),
    )
    assert feed_path.exists()
    assert (feed_dir / "episodes.json").exists()

    root = ElementTree.fromstring(feed_path.read_text(encoding="utf-8"))
    items = root.findall("channel/item")
    assert len(items) == 1
    assert int(items[0].find("enclosure").get("length")) == 104


def test_update_feed_appends_and_sorts_newest_first(tmp_path):
    meta = _meta()
    feed_dir = tmp_path / "podcast"
    for day in (2, 9):  # June 2 then June 9
        audio = tmp_path / f"digest-2025-06-{day:02d}.wav"
        audio.write_bytes(b"data")
        update_feed(feed_dir, meta, audio, f"Digest {day}", "d",
                    datetime(2025, 6, day, tzinfo=timezone.utc))

    root = ElementTree.fromstring((feed_dir / "feed.xml").read_text(encoding="utf-8"))
    titles = [it.find("title").text for it in root.findall("channel/item")]
    assert titles == ["Digest 9", "Digest 2"]  # newest first


def test_update_feed_is_idempotent_per_filename(tmp_path):
    meta = _meta()
    feed_dir = tmp_path / "podcast"
    audio = tmp_path / "digest-2025-06-02.wav"
    audio.write_bytes(b"data")
    update_feed(feed_dir, meta, audio, "First", "d", datetime(2025, 6, 2, tzinfo=timezone.utc))
    update_feed(feed_dir, meta, audio, "Updated", "d", datetime(2025, 6, 2, tzinfo=timezone.utc))

    root = ElementTree.fromstring((feed_dir / "feed.xml").read_text(encoding="utf-8"))
    items = root.findall("channel/item")
    assert len(items) == 1  # same filename -> replaced, not duplicated
    assert items[0].find("title").text == "Updated"


def test_update_feed_caps_at_max_episodes(tmp_path):
    meta = _meta(max_episodes=3)
    feed_dir = tmp_path / "podcast"
    for day in range(1, 8):  # 7 episodes, cap 3
        audio = tmp_path / f"d-{day}.wav"
        audio.write_bytes(b"x")
        update_feed(feed_dir, meta, audio, f"D{day}", "d",
                    datetime(2025, 6, day, tzinfo=timezone.utc))

    root = ElementTree.fromstring((feed_dir / "feed.xml").read_text(encoding="utf-8"))
    assert len(root.findall("channel/item")) == 3


def test_feedmeta_from_dict_defaults():
    meta = FeedMeta.from_dict(None)
    assert meta.max_episodes == 50
    meta2 = FeedMeta.from_dict({"title": "X", "base_url": "https://h/"})
    assert meta2.title == "X"
