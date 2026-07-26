from mediawhisperer.transform.topics import extract_keyphrases, top_themes

COASTER = (
    "The new roller coaster opened this weekend. "
    "Fans rode the roller coaster all day. "
    "The roller coaster is the fastest in the park."
)


def test_extract_finds_recurring_bigram():
    phrases = extract_keyphrases(COASTER, limit=5)
    assert "Roller Coaster" in phrases


def test_bigram_suppresses_its_component_unigram():
    # "coaster" should not appear on its own once "roller coaster" is chosen.
    phrases = [p.lower() for p in extract_keyphrases(COASTER, limit=5)]
    assert "roller coaster" in phrases
    assert "coaster" not in phrases


def test_limit_is_respected():
    text = " ".join(f"word{i} word{i}" for i in range(20))
    assert len(extract_keyphrases(text, limit=3)) <= 3


def test_empty_text_returns_empty():
    assert extract_keyphrases("", limit=5) == []


def test_top_themes_prefers_cross_item_recurrence():
    # "star wars" appears in two items; "parade" in only one. Themes should
    # rank the cross-item topic first.
    per_item = [
        ["Star Wars", "Cantina"],
        ["Star Wars", "Ride"],
        ["Parade"],
    ]
    themes = top_themes(per_item, limit=5)
    assert themes[0] == "Star Wars"


def test_top_themes_handles_no_recurrence():
    per_item = [["A"], ["B"], ["C"]]
    themes = top_themes(per_item, limit=2)
    assert len(themes) == 2
