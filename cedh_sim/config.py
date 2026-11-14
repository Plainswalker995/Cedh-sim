"""Local settings, kept in config.json next to the program (never committed: it names your deck).

Keys (all optional):
  forge_home   folder of the patched Forge build (default: ./forge, or the FORGE_HOME variable)
  deck         your deck: a .dck file, an exported list or a Moxfield link (default: decks/my-deck.dck)
  moxfield     a Moxfield link that `auto` tries to read fresh before each batch
  pool_source  folder of opponent lists for refresh-pool (default: decks/pool-meta)
  meta_file    tab-separated meta shares for those lists (default: data/meta.tsv)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_CFG: dict | None = None


def get(key: str, default=None):
    global _CFG
    if _CFG is None:
        p = ROOT / "config.json"
        try:
            _CFG = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except (OSError, json.JSONDecodeError):
            _CFG = {}
    return _CFG.get(key, default)


def forge_home() -> Path:
    env = os.environ.get("FORGE_HOME")
    if env:
        return Path(env)
    cfg = get("forge_home")
    return Path(cfg) if cfg else ROOT / "forge"


def path(key: str, default: Path) -> Path:
    v = get(key)
    if not v:
        return default
    p = Path(v).expanduser()
    return p if p.is_absolute() else ROOT / p
