from mediawhisperer.transform.captions import parse_srt, parse_subtitles, parse_vtt

# A realistic YouTube auto-caption snippet: header, cue timings, inline timing
# tags, positioning flags, and rolling-caption line repetition.
AUTO_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.500 align:start position:0%
welcome back to the channel

00:00:02.500 --> 00:00:05.000 align:start position:0%
welcome back to the channel
today<00:00:03.100><c> we</c><00:00:03.400><c> tour</c>

00:00:05.000 --> 00:00:07.000
today we tour the new land
"""

SIMPLE_SRT = """1
00:00:00,000 --> 00:00:02,000
Hello and welcome.

2
00:00:02,000 --> 00:00:04,000
Today we tour the new land.
"""


def test_vtt_strips_header_timings_and_tags():
    text = parse_vtt(AUTO_VTT)
    assert "WEBVTT" not in text
    assert "-->" not in text
    assert "<c>" not in text
    assert "00:00" not in text
    assert "align" not in text


def test_vtt_collapses_rolling_duplicates():
    text = parse_vtt(AUTO_VTT)
    # "welcome back to the channel" appears twice in the raw cues; once here.
    assert text.lower().count("welcome back to the channel") == 1
    # The extending line ("today" -> "today we tour the new land") collapses.
    assert text.lower().count("today we tour") == 1
    assert "new land" in text.lower()


def test_srt_parses_to_prose():
    text = parse_srt(SIMPLE_SRT)
    assert text == "Hello and welcome. Today we tour the new land."


def test_parse_subtitles_dispatches_on_format():
    assert parse_subtitles(SIMPLE_SRT, "srt") == parse_srt(SIMPLE_SRT)
    assert parse_subtitles(AUTO_VTT, "vtt") == parse_vtt(AUTO_VTT)


def test_empty_input_yields_empty_string():
    assert parse_vtt("WEBVTT\n\n") == ""
    assert parse_srt("") == ""
