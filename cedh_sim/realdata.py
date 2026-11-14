"""Real-world data: facts only, from public sources and your own games.

- data/my-games.jsonl: your own games, one line each (`cedh-sim log-game`).
- data/meta-edhtop16.tsv: commander meta shares (EDHTop16, public pages).
- data/real-games.jsonl: facts about real games from public pages (tournament records, video titles):
  commanders in the pod, seat if stated, winner, win turn and how, the source and a reliability label.
  Never text, video or audio of anyone's content.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MY_GAMES = ROOT / "data" / "my-games.jsonl"
REAL_GAMES = ROOT / "data" / "real-games.jsonl"


def log_my_game(text: str = "", deck: str | None = None, seat: int | None = None, result: str | None = None,
                turn: int | None = None, how: str | None = None, opponents: str | None = None) -> dict:
    """Store one of your games. Fields can be given directly or read from a sentence like
    'I played Tymna/Kraum, seat 2, won on turn 4 by Thassa's Oracle vs Kinnan, Sisay, Rog/Thras'."""
    t = text or ""
    if seat is None:
        m = re.search(r"seat\s*(\d)", t, re.I)
        seat = int(m.group(1)) if m else None
    if result is None:
        result = "win" if re.search(r"\bwon\b|\bwin\b", t, re.I) else "loss" if re.search(r"\blost\b|\bloss\b", t, re.I) \
            else "draw" if re.search(r"\bdraw\b|\bdrew\b", t, re.I) else None
    if turn is None:
        m = re.search(r"turn\s*(\d+)", t, re.I)
        turn = int(m.group(1)) if m else None
    if how is None:
        m = re.search(r"\b(?:by|with|via)\s+([^,;.]+?)(?:\s+(?:vs|against)\b|[,;.]|$)", t, re.I)
        how = m.group(1).strip() if m else None
    if opponents is None:
        m = re.search(r"\b(?:vs\.?|against)\s+(.+)$", t, re.I)
        opponents = m.group(1).strip() if m else None
    if deck is None:
        m = re.search(r"\bplayed\s+([^,;]+?)(?:,|\s+seat|\s+in seat|$)", t, re.I)
        deck = m.group(1).strip() if m else "my deck"
    rec = {"date": dt.date.today().isoformat(), "deck": deck, "seat": seat, "result": result, "turn": turn,
           "how": how, "opponents": [o.strip() for o in re.split(r",|\band\b", opponents) if o.strip()] if opponents else [],
           "source": "own game", "reliability": "first-hand", "note": t or None}
    MY_GAMES.parent.mkdir(parents=True, exist_ok=True)
    with open(MY_GAMES, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def counts() -> dict:
    real = load(REAL_GAMES)
    by_source = {}
    for r in real:
        by_source[r.get("source_kind", "other")] = by_source.get(r.get("source_kind", "other"), 0) + 1
    return {"my_games": len(load(MY_GAMES)), "real_games": len(real), "real_by_source": by_source}
