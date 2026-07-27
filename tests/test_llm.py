import pytest

from mediawhisperer.models import Transcript
from mediawhisperer.transform.summarize import get_summarizer
from mediawhisperer.transform.llm import LLMSummarizer, _parse_response

TRANSCRIPT = Transcript(
    item_id="x",
    title="Galaxy's Edge Turns Five",
    source_name="Parks Pod",
    text=(
        "The Star Wars land marked five years. Rise of the Resistance is more "
        "reliable now. Star Wars fans still debate a second Star Wars land."
    ),
)


def _fake_chat(monkeypatch, content: str, capture: dict | None = None):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": content}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        if capture is not None:
            capture["url"] = url
            capture["headers"] = headers
            capture["json"] = json
        return FakeResponse()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)


def test_llm_is_registered():
    # Constructed via the registry (ollama needs no key).
    assert isinstance(get_summarizer("llm", provider="ollama"), LLMSummarizer)


def test_llm_parses_json_summary_and_highlights(monkeypatch):
    capture: dict = {}
    _fake_chat(
        monkeypatch,
        '{"summary": "Five years of Galaxy\'s Edge.", "highlights": ["Ride is reliable now.", "Blue milk still pricey."]}',
        capture,
    )
    note = get_summarizer("llm", provider="ollama").summarize(TRANSCRIPT, highlights=4)
    assert note.summary == "Five years of Galaxy's Edge."
    assert note.highlights == ["Ride is reliable now.", "Blue milk still pricey."]
    # Topics are computed deterministically, not from the model.
    assert note.topics  # non-empty
    # Ollama endpoint + model used.
    assert capture["url"].startswith("http://localhost:11434/v1")


def test_llm_strips_code_fence(monkeypatch):
    _fake_chat(monkeypatch, '```json\n{"summary": "Fenced.", "highlights": []}\n```')
    note = get_summarizer("llm", provider="ollama").summarize(TRANSCRIPT)
    assert note.summary == "Fenced."


def test_llm_falls_back_on_non_json(monkeypatch):
    _fake_chat(monkeypatch, "Just a plain sentence, not JSON.")
    note = get_summarizer("llm", provider="ollama").summarize(TRANSCRIPT)
    assert note.summary == "Just a plain sentence, not JSON."
    assert note.highlights == []


def test_llm_respects_highlight_limit(monkeypatch):
    _fake_chat(monkeypatch, '{"summary": "s", "highlights": ["a","b","c","d","e"]}')
    note = get_summarizer("llm", provider="ollama").summarize(TRANSCRIPT, highlights=2)
    assert len(note.highlights) == 2


def test_hosted_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    summ = get_summarizer("llm", provider="groq")
    with pytest.raises(RuntimeError, match="API key"):
        summ.summarize(TRANSCRIPT)


def test_provider_presets_set_base_url_and_model():
    groq = LLMSummarizer(provider="groq", api_key="k")
    assert "groq.com" in groq.base_url
    assert groq.model == "llama-3.3-70b-versatile"
    openai = LLMSummarizer(provider="openai", api_key="k")
    assert openai.model == "gpt-4o-mini"


def test_explicit_base_url_and_model_override_preset():
    summ = LLMSummarizer(provider="ollama", base_url="http://host:9999/v1/", model="qwen2.5")
    assert summ.base_url == "http://host:9999/v1"  # trailing slash trimmed
    assert summ.model == "qwen2.5"


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        LLMSummarizer(provider="nope")


def test_parse_response_helper():
    assert _parse_response('{"summary":"a","highlights":["x"]}', 4) == ("a", ["x"], [])
    assert _parse_response(
        '{"summary":"a","highlights":["x"],"key_facts":["opened May 27th"]}', 4
    ) == ("a", ["x"], ["opened May 27th"])
    assert _parse_response("not json", 4) == ("not json", [], [])
