# Media Whisperer

The goal of this project is to automatically download a feed to consume the latest information and compile it into a digestable format either as a quick notes page or as a easy to listen to podcast.

## Use Case

I'm a huge Disney fan that listen to every Podcast under the sun regarding the parks, Star Wars and Marvel.  I also watch a lot of YouTube videos, read blogs, follow creators, and so on.

Rather than consuming it all individually, I plan to scoop up the content once a day or week.  Then I can compile a list of interesting news, stories and facts.

## How it works

MediaWhisperer is an ETL pipeline. You describe the feeds you follow in one YAML
file, and each run walks them end to end:

```
 discover → (download) → transcribe → summarize → compile → render
```

The output of a run is a set of deliverables, all built from the same digest so
the written and spoken versions never drift apart:

- **`digest-YYYY-MM-DD.md`** — a skimmable notes page, grouped by source, with a
  short summary, highlight bullets, and topic tags per item.
- **`digest-YYYY-MM-DD.script.txt`** — a listen-ready narration script that a
  voice backend can turn into your own daily audio briefing.
- **`digest-YYYY-MM-DD.html`** — an optional self-contained HTML page (enable
  with `emit_html: true`).

### What's everyone talking about?

Each item is tagged with its own keyphrases, and those are aggregated across the
whole run into the digest's **themes** — the topics showing up in more than one
feed. That turns a pile of separate summaries into a single answer to "what's
the big story across everything I follow this week?", surfaced at the top of the
notes page and the audio intro.

### Signal over noise: cross-feed stories

When several shows cover the same thing in one run, the digest clusters them
into a single **"Top stories across your feeds"** entry — the story's key
topics, how many sources covered it, and links to each — so you see the story
once, with its sources, instead of five near-identical summaries.

### Jump straight to the moment

When a transcript has timing (Whisper, faster-whisper, or captions), every
highlight is tagged with its **timestamp** in the episode. For YouTube that
becomes a clickable deep link that opens the video at that exact second; for
podcasts it's a `M:SS` marker.

### Subscribe to your own briefing

Turn the audio digests into a real, subscribable podcast. With `emit_feed: true`
and an audio voice backend, each run appends an episode to a standard podcast
RSS feed (`output/podcast/feed.xml`). Host `output_dir` on any static web
server, point `feed.base_url` at it, and add the feed URL to your podcast app —
your daily digest shows up like any other show.

### Swappable backends

Every expensive stage is pluggable, and the **defaults run fully offline** — no
API keys, no multi-gigabyte model downloads — so a fresh checkout produces a
real digest in seconds. Upgrade any stage when you want more quality:

| Stage       | Default (offline)            | Opt-in upgrade                          |
|-------------|------------------------------|-----------------------------------------|
| Transcribe  | `feed` (use show notes)      | `captions` (reuse a video's subtitles), `faster-whisper` (fast local STT), `whisper` |
| Summarize   | `extractive` (no network)    | `llm` (abstractive, via Ollama/Groq/OpenAI/Gemini) |
| Text-to-speech | `script` (writes the text) | `piper` (neural offline), `pyttsx3` (offline), `elevenlabs` (neural cloud) |

The `captions` transcriber pulls a YouTube video's existing subtitles (creator
or auto-generated) with `yt-dlp` and skips audio processing entirely — when the
creator already captioned the video, those captions *are* the script. It falls
back to the feed description for uncaptioned videos.

Downloading media uses `yt-dlp`. Transcripts are cached by item, so re-running a
feed only does new work.

### Best quality for free (recommended stack)

Every one of these runs **locally at no cost** (you only spend your own compute)
and is a big step up from the offline defaults. Install the extras and point a
config at them:

```bash
pip install -e '.[faster-whisper,piper,youtube]'
# plus a local model server for summaries, free: https://ollama.com  ->  `ollama pull llama3.1`
```

```yaml
backends:
  transcriber: faster-whisper   # near-SOTA speech-to-text, runs on CPU
  summarizer: llm               # real abstractive summaries
  tts: piper                    # natural neural voice, offline
  options:
    model: distil-large-v3      # faster-whisper model
    provider: ollama            # llm provider (local, free)
    # For Piper, point at a downloaded .onnx voice:
    # model: /path/to/en_US-lessac-medium.onnx

sources:
  # Use free, exact captions for YouTube; transcribe audio for podcasts.
  - name: A YouTube Channel
    kind: youtube
    url: https://www.youtube.com/feeds/videos.xml?channel_id=UC...
    transcriber: captions       # per-source override
  - name: A Podcast
    kind: podcast
    url: https://example.com/feed.xml
    # inherits faster-whisper from the global backend
```

Prefer not to tie up your machine? Swap `provider: ollama` for `groq` or
`gemini` (generous free tiers) and set the matching `*_API_KEY` — a personal
daily digest realistically stays free. See the per-provider notes in
[`config.example.yaml`](config.example.yaml).

### Only new content, every run

By default a run only surfaces items it hasn't digested before (`skip_seen`), so
a daily or weekly run gives you just what's new — no repeats. The set of already
-digested items is tracked in the cache. To re-compile everything regardless:

```bash
mediawhisperer run -c config.yaml --force
```

## Quick start

```bash
# 1. Install (core deps only; the pipeline runs with just these)
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Create a config
mediawhisperer init                 # writes a starter config.yaml
#   ...then edit it to point at the podcasts / channels you follow

# 3. Compile your digest
mediawhisperer run -v
```

Already have podcast subscriptions? Export them from your podcast app as OPML
and bring them all in at once:

```bash
mediawhisperer import-opml my-subscriptions.opml
```

List what you've configured without running anything:

```bash
mediawhisperer sources
```

### Enabling the heavier backends

```bash
pip install -e '.[whisper]'   # real speech-to-text
pip install -e '.[youtube]'   # download YouTube videos
pip install -e '.[voice]'     # render the script to an audio file
pip install -e '.[all]'       # everything
```

Then point the backends at them in `config.yaml`:

```yaml
backends:
  transcriber: whisper
  tts: pyttsx3
  options:
    model: base   # whisper model size
```

For a neural cloud voice, use the `elevenlabs` backend and keep the key out of
the config file via an environment variable:

```yaml
backends:
  tts: elevenlabs
  options:
    voice_id: 21m00Tcm4TlvDq8ikWAM   # optional; or ELEVENLABS_VOICE_ID
```

```bash
export ELEVENLABS_API_KEY=sk-...
mediawhisperer run
```

## Scheduling

The tool is built for unattended runs — it's resilient per item, exits cleanly,
and (with `skip_seen` on) only compiles what's new each time. Ready-to-edit cron,
systemd, and launchd recipes live in [`deploy/`](deploy/); use `--log-file` to
capture timestamped progress:

```bash
mediawhisperer run -c config.yaml --log-file mediawhisperer.log
```

## Configuration

See [`config.example.yaml`](config.example.yaml) for a documented template. Each
source needs a `name`, a `kind` (`podcast` or `youtube`), and a `url`. Optional
per-source knobs: `lookback_days`, `max_items`, and `enabled`.

## Project layout

```
src/mediawhisperer/
├── config.py         # YAML config loading
├── models.py         # dataclasses that flow through the pipeline
├── store.py          # local transcript/media cache
├── pipeline.py       # the ETL orchestrator
├── cli.py            # command-line entry point
├── extract/          # sources → media items (podcast RSS, youtube)
├── transform/        # media → transcript → notes (transcribe, summarize)
└── load/             # digest → notes page + script + audio (render, tts)
```

## Development

```bash
pip install -e '.[dev]'
pytest
```

## The Plan

### Extract

- [x] Download Podcast Script
- [x] Download YouTube Videos Script

### Transform

- [x] Convert Audio/Video into Text
- [x] Compile Transformed Text into Notes
- [x] Convert Notes into Plain Text

### Load

- [x] Convert Plain Text into Podcast

## The Tools

OpenAI Whisper
youtube-dl / yt-dlp
feedparser
pyttsx3 / ElevenLabs
