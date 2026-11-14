"""Deck lists: read Moxfield (API JSON or exported text) and write Forge .dck files.

Supported inputs
- A Moxfield URL or deck id (https://moxfield.com/decks/<id>): fetched from Moxfield's
  deck API once, on your own machine (see moxfield.py).
- A text file: Moxfield "Export" text (``1 Card Name (SET) 123 *F*``), a plain list
  (``1 Card Name`` or just ``Card Name``), MTGO/Arena style with ``Commander`` /
  ``Deck`` / ``Sideboard`` headers, or a line ``Commanders: A; B``.
- An existing Forge ``.dck`` file (used as is).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Section headers we understand in text exports. Everything is lower-cased first.
COMMANDER_HEADERS = {"commander", "commanders", "commander:", "commanders:", "// commander",
                     "// commanders", "command zone"}
MAIN_HEADERS = {"deck", "main", "mainboard", "main deck", "// mainboard", "// deck", "deck:", "mainboard:"}
SKIP_HEADERS = {"sideboard", "sideboard:", "// sideboard", "maybeboard", "maybeboard:", "// maybeboard",
                "considering", "tokens", "tokens:", "// tokens", "attractions", "stickers"}

TYPE_HEADER_RE = re.compile(r"^(creatures?|sorcery|sorceries|instants?|artifacts?|enchantments?|lands?|"
                            r"planeswalkers?|battles?|other|spells|kindred|tribal|mana|ramp)\s*(\(\d+\))?:?$",
                            re.IGNORECASE)
LINE_RE = re.compile(r"^\s*(?:(\d+)\s*x?\s+)?(.+?)\s*$", re.IGNORECASE)
# Moxfield export tail: " (SET) 123", optional " *F*" / " *E*" foil marks, optional "#tags".
TAIL_RE = re.compile(r"\s+\([A-Za-z0-9]{2,6}\)(\s+[A-Za-z0-9\-★]+)?(\s+\*[A-Z]+\*)*\s*$")
FOIL_RE = re.compile(r"(\s+\*[A-Z]+\*)+\s*$")
TAG_RE = re.compile(r"\s+#\S.*$")


@dataclass
class Deck:
    name: str
    commanders: list[str] = field(default_factory=list)
    main: dict[str, int] = field(default_factory=dict)
    source: str = ""

    @property
    def size(self) -> int:
        return len(self.commanders) + sum(self.main.values())

    def add(self, card: str, qty: int = 1) -> None:
        card = normalize_name(card)
        if card:
            self.main[card] = self.main.get(card, 0) + qty

    def problems(self) -> list[str]:
        out = []
        if not self.commanders:
            out.append("no commander found (use --commander or a 'Commander' section)")
        if self.size != 100:
            out.append(f"deck has {self.size} cards including commanders, not 100")
        basics = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
                  "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
                  "Snow-Covered Mountain", "Snow-Covered Forest"}
        multi_ok = {"Relentless Rats", "Shadowborn Apostle", "Persistent Petitioners", "Rat Colony",
                    "Dragon's Approach", "Seven Dwarves", "Slime Against Humanity", "Templar Knight",
                    "Hare Apparent", "Tempest Hawk", "Nazgûl", "Cid, Timeless Artificer"}
        for card, n in self.main.items():
            if n > 1 and card not in basics and card not in multi_ok:
                out.append(f"{n} copies of {card} (Commander is singleton)")
        return out


def normalize_name(name: str) -> str:
    name = TAG_RE.sub("", name.strip())
    name = TAIL_RE.sub("", name)
    name = FOIL_RE.sub("", name)
    name = name.replace("’", "'").replace("`", "'").strip()
    # Double-faced cards: Forge wants the front face name.
    if " // " in name:
        name = name.split(" // ")[0].strip()
    return name


def parse_text(text: str, name: str = "Deck", commanders: list[str] | None = None) -> Deck:
    deck = Deck(name=name, source="text")
    section = "main"
    saw_blank_after_main = False
    pending_tail: list[tuple[str, int]] = []  # cards after a blank line at the end (MTGO-style commander)
    for raw in text.splitlines():
        line = raw.strip()
        low = line.lower()
        if not line:
            if section == "main" and deck.main:
                saw_blank_after_main = True
            continue
        if line.startswith("#"):
            continue
        if low.startswith("name="):
            deck.name = line.split("=", 1)[1].strip() or deck.name
            continue
        m_cmd = re.match(r"^commanders?\s*:\s*(.+)$", line, re.IGNORECASE)
        if m_cmd and not re.match(r"^\d", line):
            for part in re.split(r";|\s\+\s", m_cmd.group(1)):
                if part.strip():
                    deck.commanders.append(normalize_name(part))
            continue
        if low in COMMANDER_HEADERS:
            section = "commander"
            continue
        if low in MAIN_HEADERS or TYPE_HEADER_RE.match(line):
            section = "main"
            continue
        if low in SKIP_HEADERS or low.startswith("sideboard") or low.startswith("maybeboard"):
            section = "skip"
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        qty = int(m.group(1) or 1)
        card = normalize_name(m.group(2))
        if not card:
            continue
        if section == "commander":
            deck.commanders.append(card)
        elif section == "main":
            if saw_blank_after_main:
                pending_tail.append((card, qty))
            else:
                deck.add(card, qty)
    # MTGO/Moxfield "copy for MTGO": 99 cards, blank line, then the commander(s).
    if pending_tail:
        if not deck.commanders and len(pending_tail) <= 2 and sum(q for _, q in pending_tail) <= 2:
            deck.commanders.extend(c for c, _ in pending_tail)
        else:
            for c, q in pending_tail:
                deck.add(c, q)
    if commanders:
        deck.commanders = [normalize_name(c) for c in commanders]
    # A commander listed in the main section too: drop it from the 99.
    for c in deck.commanders:
        if c in deck.main:
            deck.main[c] -= 1
            if deck.main[c] <= 0:
                del deck.main[c]
    return deck


def parse_moxfield_json(data: dict) -> Deck:
    """Moxfield deck API JSON, v3 (boards.<board>.cards.<id>) or v2 (<board>.<name>)."""
    deck = Deck(name=data.get("name") or "Moxfield deck", source="moxfield")
    boards = data.get("boards")
    if isinstance(boards, dict):  # v3
        def entries(board):
            return ((boards.get(board) or {}).get("cards") or {}).values()
    else:  # v2
        def entries(board):
            return (data.get(board) or {}).values()
    for e in entries("commanders"):
        deck.commanders.append(normalize_name(e["card"]["name"]))
    for board in ("mainboard", "companions"):
        for e in entries(board):
            deck.add(e["card"]["name"], int(e.get("quantity", 1)))
    return deck


def load_dck(path: Path) -> Deck:
    deck = Deck(name=path.stem, source=str(path))
    section = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].lower()
            continue
        if section == "metadata" and line.lower().startswith("name="):
            deck.name = line.split("=", 1)[1]
            continue
        m = re.match(r"^(\d+)\s+(.+)$", line)
        if not m:
            continue
        card = m.group(2).split("|")[0].strip()
        if section == "commander":
            deck.commanders.extend([card] * int(m.group(1)))
        elif section == "main":
            deck.add(card, int(m.group(1)))
    return deck


def write_dck(deck: Deck, path: Path) -> Path:
    lines = ["[metadata]", f"Name={deck.name}", "[Commander]"]
    lines += [f"1 {c}" for c in deck.commanders]
    lines.append("[Main]")
    lines += [f"{n} {c}" for c, n in sorted(deck.main.items())]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_any(spec: str, name: str | None = None, commanders: list[str] | None = None,
             cache_dir: Path | None = None) -> Deck:
    """A Moxfield URL/id, a .json API dump, a .dck file or a text list."""
    from . import moxfield
    p = Path(spec).expanduser()
    if p.exists():
        if p.suffix.lower() == ".dck":
            deck = load_dck(p)
        elif p.suffix.lower() == ".json":
            deck = parse_moxfield_json(json.loads(p.read_text(encoding="utf-8")))
        else:
            deck = parse_text(p.read_text(encoding="utf-8"), name=name or p.stem, commanders=commanders)
    elif moxfield.deck_id(spec):
        deck = moxfield.fetch_deck(spec, cache_dir=cache_dir)
    else:
        raise FileNotFoundError(f"Not a file or a Moxfield link: {spec}")
    if name:
        deck.name = name
    if commanders:
        deck.commanders = [normalize_name(c) for c in commanders]
    return deck
