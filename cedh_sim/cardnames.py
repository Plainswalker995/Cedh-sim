"""Card names Forge knows, so deck lists can be checked before a game is played.

The index is built once from Forge's card scripts (res/cardsfolder) and cached as JSON.
Every face name maps to the name Forge wants in a deck file: the front face, or "A // B"
for split cards.
"""
from __future__ import annotations

import json
import os
import unicodedata
from pathlib import Path

from . import config

FORGE_HOME = config.forge_home()
CACHE = Path(__file__).resolve().parent.parent / "cache" / "card-index.json"


def _key(name: str) -> str:
    name = name.replace("’", "'").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))


def build_index() -> dict[str, str]:
    folder = FORGE_HOME / "forge-gui" / "res" / "cardsfolder"
    index: dict[str, str] = {}
    for f in folder.rglob("*.txt"):
        names, split = [], False
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("Name:"):
                    names.append(line[5:].strip())
                elif line.startswith("AlternateMode:") and "Split" in line:
                    split = True
        except OSError:
            continue
        if not names:
            continue
        deck_name = " // ".join(names[:2]) if split and len(names) >= 2 else names[0]
        for n in names:
            index.setdefault(_key(n), deck_name)
        index[_key(deck_name)] = deck_name
    return index


_INDEX: dict[str, str] | None = None


def index() -> dict[str, str]:
    global _INDEX
    if _INDEX is None:
        if CACHE.exists():
            _INDEX = json.loads(CACHE.read_text(encoding="utf-8"))
        else:
            _INDEX = build_index()
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(_INDEX), encoding="utf-8")
    return _INDEX


def resolve(name: str) -> str | None:
    """The deck-file name for a card, or None when Forge doesn't know it."""
    idx = index()
    hit = idx.get(_key(name))
    if hit is None and " // " in name:
        hit = idx.get(_key(name.split(" // ")[0]))
    if hit is None and "/" in name and " // " not in name:
        hit = idx.get(_key(name.split("/")[0]))
    return hit
