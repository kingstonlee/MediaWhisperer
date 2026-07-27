from mediawhisperer.models import Transcript
from mediawhisperer.transform.facts import extract_key_facts, fact_count, fact_density
from mediawhisperer.transform.summarize import ExtractiveSummarizer

DETAILED = (
    "The coaster opens May 27th, 2025 at the resort. "
    "It cost 200 million dollars and reaches 91 mph. "
    "CEO Bob Iger said it is the biggest investment yet. "
    "The weather that day was pleasant. "
    "Tickets rose 8% to 189 dollars this season."
)


def test_fact_count_detects_specifics():
    assert fact_count("It reaches 91 mph and cost 200 million dollars.") >= 2
    assert fact_count("The weather was nice.") == 0


def test_fact_count_detects_dates_and_names():
    assert fact_count("Bob Iger spoke on May 27th, 2025.") >= 2


def test_fact_density_is_length_normalized():
    dense = fact_density("Opened May 27th at 9:00 for 189 dollars.")
    sparse = fact_density("It was a very nice and pleasant sort of a day overall.")
    assert dense > sparse


def test_extract_key_facts_returns_detailful_sentences():
    facts = extract_key_facts(DETAILED, limit=3)
    assert facts
    joined = " ".join(facts).lower()
    # The fact-free "weather was pleasant" sentence must not crowd out specifics.
    assert "pleasant" not in joined or any(c.isdigit() for c in " ".join(facts))
    assert any("mph" in f or "dollars" in f or "%" in f or "27th" in f.lower() for f in facts)


def test_extract_key_facts_empty_when_no_details():
    assert extract_key_facts("It was nice. We had fun. The end.", limit=5) == []


def test_extract_key_facts_respects_limit():
    assert len(extract_key_facts(DETAILED, limit=2)) <= 2


def test_extractive_summary_populates_key_facts():
    t = Transcript(item_id="x", title="Coaster", source_name="Parks", text=DETAILED)
    note = ExtractiveSummarizer().summarize(t, summary_sentences=2, highlights=2)
    assert note.key_facts
    # A concrete detail is present in the facts list.
    assert any(any(ch.isdigit() for ch in fact) for fact in note.key_facts)


def test_detail_bonus_favors_specific_sentences_in_summary():
    # A fact-dense sentence should be selected over a bland one of similar topic.
    text = (
        "The park is popular with many people who visit often. "
        "The park set a record with 21 million visitors in 2024, up 12%. "
        "People enjoy the park and have a nice time at the park. "
        "The park is a place that people go to for the park experience."
    )
    t = Transcript(item_id="y", title="Park", source_name="News", text=text)
    note = ExtractiveSummarizer().summarize(t, summary_sentences=1, highlights=1)
    assert "21 million" in note.summary or "12%" in note.summary
