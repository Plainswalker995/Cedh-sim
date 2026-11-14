"""Fetch one Moxfield deck by link or id.

Moxfield has no official public API. This makes a single request to the JSON endpoint
its own deck page uses, only when you run the command, and caches the result so the
same deck is never fetched twice. If Moxfield refuses (Cloudflare check, 403, rate
limit), export the deck instead: on the deck page choose More > Export > Copy as plain
text (or Download .txt), save it to a file and pass that file.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from .decks import Deck, parse_moxfield_json

ID_RE = re.compile(r"(?:moxfield\.com/decks/)?([A-Za-z0-9_-]{16,32})/?(?:[?#].*)?$")
ENDPOINTS = [
    "https://api2.moxfield.com/v3/decks/all/{id}",
    "https://api.moxfield.com/v2/decks/all/{id}",
]
USER_AGENT = "cedh-sim/1.0 (personal deck simulator; single deck fetch)"


class MoxfieldError(RuntimeError):
    pass


def deck_id(spec: str) -> str | None:
    spec = spec.strip()
    if "/" in spec and "moxfield.com" not in spec:
        return None
    m = ID_RE.search(spec)
    return m.group(1) if m else None


def fetch_deck(spec: str, cache_dir: Path | None = None, timeout: int = 30) -> Deck:
    did = deck_id(spec)
    if not did:
        raise MoxfieldError(f"Not a Moxfield deck link or id: {spec}")
    cache = (cache_dir / f"moxfield-{did}.json") if cache_dir else None
    if cache and cache.exists():
        return parse_moxfield_json(json.loads(cache.read_text(encoding="utf-8")))
    errors = []
    for url in ENDPOINTS:
        req = urllib.request.Request(url.format(id=did), headers={
            "User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            deck = parse_moxfield_json(data)
            if cache:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(raw, encoding="utf-8")
            deck.source = f"https://moxfield.com/decks/{did}"
            return deck
        except urllib.error.HTTPError as e:
            errors.append(f"{e.code} from {url.split('/')[2]}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            errors.append(f"{type(e).__name__} from {url.split('/')[2]}")
    raise MoxfieldError(
        "Moxfield refused the download (" + "; ".join(errors) + ").\n"
        "Export the deck instead: on the deck page choose More > Export > Copy as plain text,\n"
        "paste it into a .txt file and pass that file in place of the link.")
