"""Abstractive summarization via an OpenAI-compatible chat API.

One implementation covers every provider that speaks the OpenAI
``/chat/completions` protocol, which today is almost all of them:

* **Ollama** (local, free)      -- base_url http://localhost:11434/v1, no key
* **Groq** (free tier, fast)    -- https://api.groq.com/openai/v1, GROQ_API_KEY
* **OpenAI**                    -- default base_url, OPENAI_API_KEY
* **Gemini** (free tier)        -- .../v1beta/openai/, GEMINI_API_KEY

So "run a good local model for free" and "use a cheap hosted model" are the same
code path with a different ``provider`` (or explicit ``base_url``/``model``).

The model is asked for a compact JSON object (summary + highlights); topics stay
deterministic (our own extractor) so they cost no tokens and never drift. If the
model's JSON is malformed, we degrade gracefully to using its raw text as the
summary rather than failing the item.
"""

from __future__ import annotations

import json
import os
import re

from ..models import Note, Transcript
from .summarize import Summarizer, register
from .topics import extract_keyphrases

# Provider presets: (base_url, api_key_env, default_model).
_PROVIDERS = {
    "ollama": ("http://localhost:11434/v1", None, "llama3.1"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4o-mini"),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "GEMINI_API_KEY",
        "gemini-2.0-flash",
    ),
}

_SYSTEM_PROMPT = (
    "You condense podcast and video transcripts into a tight briefing for a busy "
    "fan. Capture the actual news, stories, and facts -- not vague description. "
    "Respond ONLY with a JSON object of the form "
    '{"summary": "<2-4 sentences>", "highlights": ["<short bullet>", ...]}. '
    "No preamble, no markdown, no code fences."
)


@register("llm")
class LLMSummarizer(Summarizer):
    """Abstractive summarizer backed by an OpenAI-compatible chat endpoint."""

    def __init__(self, **options) -> None:
        super().__init__(**options)
        provider = options.get("provider", "ollama")
        preset = _PROVIDERS.get(provider)
        if preset is None:
            valid = ", ".join(sorted(_PROVIDERS))
            raise ValueError(f"Unknown LLM provider {provider!r}. Available: {valid}")
        base_default, key_env, model_default = preset

        self.base_url = (options.get("base_url") or base_default).rstrip("/")
        self.model = options.get("model") or model_default
        self.temperature = float(options.get("temperature", 0.3))
        self.timeout = int(options.get("timeout", 120))
        self.api_key = options.get("api_key") or (os.environ.get(key_env) if key_env else None)
        # Local providers (Ollama) don't need a key; hosted ones do.
        self._key_env = key_env

    def summarize(
        self,
        transcript: Transcript,
        item_url: str = "",
        published=None,
        summary_sentences: int = 3,
        highlights: int = 4,
    ) -> Note:
        content = self._complete(transcript, summary_sentences, highlights)
        summary, bullets = _parse_response(content, highlights)

        # Deterministic topics -- free, stable, no extra tokens.
        topics = extract_keyphrases(
            transcript.text, self.options.get("topics_per_item", 5)
        )
        return Note(
            item_id=transcript.item_id,
            title=transcript.title,
            source_name=transcript.source_name,
            url=item_url,
            summary=summary or transcript.text.strip()[:500],
            highlights=bullets,
            topics=topics,
            published=published,
        )

    def _complete(self, transcript: Transcript, summary_sentences: int, highlights: int) -> str:
        import requests

        if self._key_env and not self.api_key:
            raise RuntimeError(
                f"This LLM provider needs an API key. Set {self._key_env} "
                "(or put api_key under backends.options)."
            )

        user = (
            f"Title: {transcript.title}\n"
            f"Source: {transcript.source_name}\n\n"
            f"Summarize in about {summary_sentences} sentences and give up to "
            f"{highlights} highlight bullets.\n\nTranscript:\n{transcript.text}"
        )
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def _parse_response(content: str, max_highlights: int) -> tuple[str, list[str]]:
    """Pull summary + highlights out of the model's reply, tolerating slop."""
    text = content.strip()
    # Strip a ```json ... ``` fence if the model added one despite instructions.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        payload = json.loads(text)
        summary = str(payload.get("summary", "")).strip()
        highlights = [str(h).strip() for h in payload.get("highlights", []) if str(h).strip()]
        return summary, highlights[:max_highlights]
    except (json.JSONDecodeError, AttributeError, TypeError):
        # Not valid JSON -- fall back to treating the whole reply as the summary.
        return text, []
