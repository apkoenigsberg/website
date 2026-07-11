"""
Genius scraper for Carly Rae Jepsen — album-first approach for accurate album names.

Usage:
    python scraper.py                  # full scrape
    python scraper.py --limit 5        # first 5 songs only (for testing)
    python scraper.py --resume         # skip songs already in output file
"""

import json
import argparse
import os
import time
from pathlib import Path

import lyricsgenius
from dotenv import load_dotenv

load_dotenv()

ARTIST_ID = 21150  # Carly Rae Jepsen on Genius
OUTPUT_FILE = Path("songs.json")


def load_existing(path: Path) -> dict[str, dict]:
    """Load already-scraped songs keyed by api_path."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {s["api_path"]: s for s in data}


def save(songs: list[dict], path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=2)


def clean_lyrics(raw: str | None) -> str | None:
    """Strip Genius header/footer noise from lyrics."""
    if not raw:
        return None
    lines = raw.splitlines()
    if lines and lines[0].endswith("Lyrics"):
        lines = lines[1:]
    if lines and lines[-1].strip().endswith("Embed"):
        lines[-1] = lines[-1][: lines[-1].rfind("Embed")].rstrip()
    return "\n".join(lines).strip() or None


def get_all_albums(genius: lyricsgenius.Genius) -> list[dict]:
    """Fetch all albums for the artist, handling pagination."""
    albums = []
    page = 1
    while True:
        resp = genius.artist_albums(ARTIST_ID, per_page=50, page=page)
        batch = resp.get("albums", [])
        if not batch:
            break
        albums.extend(batch)
        next_page = resp.get("next_page")
        if not next_page:
            break
        page = next_page
    return albums


def get_album_tracks(genius: lyricsgenius.Genius, album_id: int) -> list[dict]:
    """Fetch all tracks for an album."""
    tracks = []
    page = 1
    while True:
        resp = genius.album_tracks(album_id, per_page=50, page=page)
        batch = resp.get("tracks", [])
        if not batch:
            break
        tracks.extend(batch)
        next_page = resp.get("next_page")
        if not next_page:
            break
        page = next_page
    return tracks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only scrape the first N songs total")
    parser.add_argument("--resume", action="store_true", help="Skip songs already saved in output file")
    args = parser.parse_args()

    token = os.getenv("GENIUS_TOKEN")
    if not token:
        raise SystemExit("GENIUS_TOKEN not set — add it to .env")

    genius = lyricsgenius.Genius(
        token,
        skip_non_songs=True,
        excluded_terms=["(Remix)", "(Live)", "(Demo)", "(Instrumental)"],
        remove_section_headers=True,
    )

    existing = load_existing(OUTPUT_FILE) if args.resume else {}
    if existing:
        print(f"Resuming — {len(existing)} songs already scraped.")

    print("Fetching albums...")
    albums = get_all_albums(genius)
    print(f"Found {len(albums)} albums.")

    # Build a flat list of (song_api_path, song_data, album_name) deduped by api_path
    seen_paths = set()
    song_queue = []  # [(album_name, release_year, track_data), ...]

    for album in albums:
        album_name = album["name"]
        release_year = (album.get("release_date_components") or {}).get("year")
        print(f"  Fetching tracklist: {album_name}")
        tracks = get_album_tracks(genius, album["id"])
        for track in tracks:
            song = track.get("song", {})
            api_path = song.get("api_path")
            if not api_path or api_path in seen_paths:
                continue
            # Only include songs by CRJ (skip featured appearances)
            primary = song.get("primary_artist", {})
            if primary.get("id") != ARTIST_ID:
                continue
            seen_paths.add(api_path)
            song_queue.append((album_name, release_year, song))

    print(f"\n{len(song_queue)} unique songs to scrape.")

    if args.limit:
        song_queue = song_queue[: args.limit]
        print(f"Limiting to {args.limit} songs.")

    results = list(existing.values())
    total = len(song_queue)

    for i, (album_name, release_year, song_data) in enumerate(song_queue, 1):
        api_path = song_data["api_path"]
        title = song_data.get("title", "Unknown")

        if api_path in existing:
            print(f"  [{i}/{total}] Skipping (already scraped): {title}")
            continue

        print(f"  [{i}/{total}] {title} — {album_name}")

        # Fetch full song with lyrics using ID directly
        try:
            song_id = song_data.get("id")
            full_song = genius.search_song(song_id=song_id) if song_id else None
            lyrics = clean_lyrics(full_song.lyrics) if full_song else None
        except Exception as e:
            print(f"    ERROR fetching lyrics: {e}")
            lyrics = None

        status = f"{len(lyrics)} chars" if lyrics else "NO LYRICS"
        print(f"    {status}")

        results.append({
            "api_path": api_path,
            "title": title,
            "album": album_name,
            "release_year": release_year,
            "url": song_data.get("url"),
            "lyrics": lyrics,
        })
        save(results, OUTPUT_FILE)

    print(f"\nDone. {len(results)} songs saved to {OUTPUT_FILE}.")
    missing = [s for s in results if not s.get("lyrics")]
    if missing:
        print(f"\n{len(missing)} songs with no lyrics:")
        for s in missing:
            print(f"  - {s['title']} ({s['album']})")


if __name__ == "__main__":
    main()
