from mediawhisperer.models import Transcript
from mediawhisperer.transform.summarize import (
    ExtractiveSummarizer,
    split_sentences,
)

LONG_TEXT = (
    "The new roller coaster opened to huge crowds this weekend. "
    "Guests waited over three hours to ride the new roller coaster on opening day. "
    "The coaster features three inversions and a top speed of sixty miles per hour. "
    "Food prices in the park increased slightly this year. "
    "A spokesperson said the coaster is the most advanced attraction the park has ever built. "
    "Parking remains free for annual passholders. "
    "The weather was sunny and warm throughout the weekend. "
    "Officials expect the new roller coaster to draw record attendance all summer."
)


def _transcript(text: str = LONG_TEXT) -> Transcript:
    return Transcript(item_id="abc", title="Coaster News", source_name="Parks", text=text)


def test_split_sentences_basic():
    assert split_sentences("Hello there. How are you? Fine!") == [
        "Hello there.",
        "How are you?",
        "Fine!",
    ]


def test_summary_has_requested_sentence_count():
    note = ExtractiveSummarizer().summarize(_transcript(), summary_sentences=3)
    assert len(split_sentences(note.summary)) == 3


def test_summary_preserves_original_order():
    note = ExtractiveSummarizer().summarize(_transcript(), summary_sentences=3)
    chosen = split_sentences(note.summary)
    positions = [LONG_TEXT.find(s) for s in chosen]
    assert positions == sorted(positions)


def test_summary_prefers_salient_topic():
    # "roller coaster" is the dominant topic; the summary should surface it.
    note = ExtractiveSummarizer().summarize(_transcript(), summary_sentences=3)
    assert "coaster" in note.summary.lower()


def test_highlights_do_not_duplicate_summary():
    note = ExtractiveSummarizer().summarize(
        _transcript(), summary_sentences=2, highlights=3
    )
    summary_sentences = set(split_sentences(note.summary))
    for bullet in note.highlights:
        assert bullet.rstrip(" .") not in {s.rstrip(" .") for s in summary_sentences}


def test_short_text_is_returned_verbatim():
    short = "Just one short note about the parade."
    note = ExtractiveSummarizer().summarize(_transcript(short), summary_sentences=3)
    assert note.summary == short
    assert note.highlights == []


def test_handles_empty_transcript_gracefully():
    note = ExtractiveSummarizer().summarize(_transcript(""), summary_sentences=3)
    assert note.summary == ""
