"""Shared lexical data for the text-processing stages.

Kept in its own module so both the summarizer and the topic extractor can use
it without importing each other (which would create a cycle).
"""

from __future__ import annotations

# A compact English stopword list. Kept inline to avoid an NLTK download.
STOPWORDS = frozenset(
    """
    a an and are as at be been but by for from had has have he her his i in into is it
    its no not of on or our so than that the their them they this to was we were what
    when which who will with would you your about after all also any because can could
    do does did just like more most much my new now one only other out over said same
    see should some such then there these those through too under up very
    whether however still back another several previously include including cover covers
    break shares share walk marked first next finally get got make made take took
    remain remains continue continues year years today day days time
    """.split()
)
