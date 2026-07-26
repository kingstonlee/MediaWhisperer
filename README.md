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

The output of a run is two deliverables, both built from the same digest so the
written and spoken versions never drift apart:

- **`digest-YYYY-MM-DD.md`** — a skimmable notes page, grouped by source, with a
  short summary and highlight bullets per item.
- **`digest-YYYY-MM-DD.script.txt`** — a listen-ready narration script that a
  voice backend can turn into your own daily audio briefing.

### Swappable backends

Every expensive stage is pluggable, and the **defaults run fully offline** — no
API keys, no multi-gigabyte model downloads — so a fresh checkout produces a
real digest in seconds. Upgrade any stage when you want more quality:

| Stage       | Default (offline)            | Opt-in upgrade                          |
|-------------|------------------------------|-----------------------------------------|
| Transcribe  | `feed` (use show notes)      | `whisper` (speech-to-text on the audio) |
| Summarize   | `extractive` (no network)    | pluggable LLM backend (registry seam)   |
| Text-to-speech | `script` (writes the text) | `pyttsx3` (offline audio file)          |

Downloading YouTube media uses `yt-dlp`. Transcripts are cached by item, so
re-running a feed only does new work.

## Quick start

```bash
# 1. Install (core deps only; the pipeline runs with just these)
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Configure your feeds
cp config.example.yaml config.yaml
#   ...edit config.yaml to point at the podcasts / channels you follow

# 3. Compile your digest
mediawhisperer run -c config.yaml -v
```

List what you've configured without running anything:

```bash
mediawhisperer sources -c config.yaml
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
