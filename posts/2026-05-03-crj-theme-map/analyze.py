#!/usr/bin/env python3
"""
Phase 2 — Theme Analysis
Sends each song's lyrics to the Claude API and extracts structured theme/sentiment data.
Output: analysis.json (one record per song, written incrementally)

Usage:
    python analyze.py              # full run
    python analyze.py --limit 5    # test with first N songs
    python analyze.py --resume     # skip already-analyzed songs (default behavior)
"""

import json
import os
import sys
import time
import argparse
import re
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MODEL = "claude-haiku-4-5-20251001"

SONGS_FILE = Path(__file__).parent / "songs.json"
ANALYSIS_FILE = Path(__file__).parent / "analysis.json"

# Rate limiting: Haiku allows generous throughput, but we add a small delay
# to be polite and avoid 429s on long runs.
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 4
RETRY_BACKOFF_BASE = 2  # seconds; doubles each retry

# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a careful, perceptive literary analyst specializing in pop music lyrics.
Your job is to identify the emotional and thematic content of song lyrics and return structured JSON.
Be specific and nuanced — avoid vague labels. Prefer precise emotional concepts over broad ones.
Do not reproduce any lyrics in your response."""

def build_user_prompt(title: str, album: str, lyrics: str) -> str:
    # Truncate very long lyrics to stay well within token limits
    max_chars = 6000
    if len(lyrics) > max_chars:
        lyrics = lyrics[:max_chars] + "\n[lyrics truncated]"

    return f"""Analyze the themes in the following song lyrics.

Song: "{title}" from the album "{album}"

Lyrics:
{lyrics}

Return a JSON object with this exact structure:
{{
  "themes": [
    {{
      "theme": "<concise theme label, 1-4 words>",
      "sentiment": "<one of: positive, negative, ambivalent>",
      "rationale": "<one sentence explaining why this theme is present and how it's treated>"
    }}
  ]
}}

Guidelines:
- Identify 2–6 themes. More is fine if the song is genuinely complex; fewer if it's focused.
- Themes should be specific emotional/relational concepts (e.g. "unrequited longing", "reckless infatuation", "self-recrimination", "euphoric desire") — not vague genre tags like "love" or "sadness".
- Sentiment reflects how the song emotionally frames that theme:
    - positive = the theme is celebrated, hopeful, joyful, or affirmed
    - negative = the theme is painful, regretful, critical, or mourned
    - ambivalent = the theme is treated with mixed or uncertain feelings
- Rationale must be one sentence. Do NOT quote lyrics.
- Return only valid JSON. No markdown, no explanation outside the JSON."""


# ── API call ──────────────────────────────────────────────────────────────────

def call_claude(title: str, album: str, lyrics: str) -> dict:
    """Call the Claude API and return the parsed themes dict. Retries on rate limit."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file:\n"
            "  ANTHROPIC_API_KEY=sk-ant-..."
        )

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    payload = {
        "model": MODEL,
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": build_user_prompt(title, album, lyrics)}
        ],
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=60)

            if resp.status_code == 429:
                wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                print(f"    ⚠ Rate limited. Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
                continue

            if resp.status_code == 529:
                wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                print(f"    ⚠ API overloaded. Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
                continue

            resp.raise_for_status()

            data = resp.json()
            raw_text = data["content"][0]["text"].strip()

            # Strip markdown code fences if present
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)

            parsed = json.loads(raw_text)
            return parsed

        except json.JSONDecodeError as e:
            print(f"    ✗ JSON parse error (attempt {attempt + 1}): {e}")
            print(f"      Raw response: {raw_text[:200]}")
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(RETRY_BACKOFF_BASE)

        except requests.exceptions.RequestException as e:
            print(f"    ✗ Request error (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))

    raise RuntimeError(f"All {MAX_RETRIES} retries failed for '{title}'")


# ── Load / save helpers ───────────────────────────────────────────────────────

def load_songs() -> list[dict]:
    with open(SONGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_analysis() -> dict:
    """Returns a dict keyed by api_path for O(1) lookup."""
    if not ANALYSIS_FILE.exists():
        return {}
    with open(ANALYSIS_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)
    return {r["song_id"]: r for r in records}


def save_analysis(analysis: dict) -> None:
    records = sorted(analysis.values(), key=lambda r: r["title"])
    with open(ANALYSIS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Phase 2: Analyze CRJ song lyrics for themes")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process the first N songs (for testing)")
    parser.add_argument("--song", type=str, default=None,
                        help="Process a single song by title (partial match, case-insensitive)")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY is not set.")
        print("Add it to your .env file:  ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    songs = load_songs()
    analysis = load_analysis()

    # Filter to songs with lyrics only
    songs_with_lyrics = [s for s in songs if s.get("lyrics")]
    print(f"Loaded {len(songs)} total songs, {len(songs_with_lyrics)} with lyrics.")

    # Apply filters
    if args.song:
        songs_with_lyrics = [
            s for s in songs_with_lyrics
            if args.song.lower() in s["title"].lower()
        ]
        print(f"Filtered to {len(songs_with_lyrics)} matching '{args.song}'.")

    if args.limit:
        songs_with_lyrics = songs_with_lyrics[:args.limit]

    already_done = sum(1 for s in songs_with_lyrics if s["api_path"] in analysis)
    to_process = [s for s in songs_with_lyrics if s["api_path"] not in analysis]

    print(f"Already analyzed: {already_done} | Remaining: {len(to_process)}")
    print()

    if not to_process:
        print("Nothing to do — all songs already analyzed.")
        return

    errors = []

    for i, song in enumerate(to_process, 1):
        title = song["title"]
        album = song.get("album", "Unknown")
        api_path = song["api_path"]
        lyrics = song["lyrics"]

        print(f"[{i}/{len(to_process)}] {title} ({album})")

        try:
            result = call_claude(title, album, lyrics)
            themes = result.get("themes", [])

            # Validate structure
            validated_themes = []
            for t in themes:
                if not isinstance(t, dict):
                    continue
                validated_themes.append({
                    "theme": str(t.get("theme", "")).strip(),
                    "sentiment": str(t.get("sentiment", "ambivalent")).strip().lower(),
                    "rationale": str(t.get("rationale", "")).strip(),
                })

            record = {
                "song_id": api_path,
                "title": title,
                "album": album,
                "release_year": song.get("release_year"),
                "url": song.get("url"),
                "themes": validated_themes,
            }

            analysis[api_path] = record
            save_analysis(analysis)  # Write after each song so progress is preserved

            theme_summary = ", ".join(
                f"{t['theme']} ({t['sentiment']})" for t in validated_themes[:3]
            )
            print(f"    ✓ {len(validated_themes)} themes: {theme_summary}{'...' if len(validated_themes) > 3 else ''}")

        except Exception as e:
            print(f"    ✗ FAILED: {e}")
            errors.append({"song": title, "error": str(e)})

        if i < len(to_process):
            time.sleep(REQUEST_DELAY_SECONDS)

    print()
    print(f"Done. {len(to_process) - len(errors)} succeeded, {len(errors)} failed.")
    print(f"Results saved to {ANALYSIS_FILE}")

    if errors:
        print("\nFailed songs:")
        for e in errors:
            print(f"  - {e['song']}: {e['error']}")


if __name__ == "__main__":
    main()
