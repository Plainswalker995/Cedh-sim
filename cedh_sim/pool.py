"""The opponent pool: real tournament lists, converted for Forge and weighted by meta share.

Sources: decks/pool-meta/*.txt (one or more top-cut lists per commander, from EDHTop16
decklist pages) and data/meta-edhtop16.tsv (each commander's share of entries).
Output: cache/pool-meta/*.dck plus weights.tsv, read by the Java runner, and a short
check report (unknown card names, wrong deck sizes).
"""
from __future__ import annotations

import csv
from pathlib import Path

from . import cardnames
from .decks import parse_text, write_dck

ROOT = Path(__file__).resolve().parent.parent


def _cmd_key(names) -> frozenset[str]:
    out = set()
    for n in names:
        r = cardnames.resolve(n) or n
        out.add(r.split(" // ")[0].lower())
    return frozenset(out)


def read_meta(path: Path) -> dict[frozenset[str], dict]:
    meta = {}
    if not path.exists():
        return meta
    rows = [l for l in path.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    for row in csv.DictReader(rows, delimiter="\t"):
        try:
            share = float(row["meta_share"])
        except (KeyError, ValueError):
            continue
        cmds = [c.strip() for c in row["commanders"].split(" / ")]
        meta[_cmd_key(cmds)] = {"rank": int(row["rank"]), "share": share, "entries": int(row["entries"]),
                                "name": row["commanders"]}
    return meta


def build(src: Path | None = None, out: Path | None = None, meta_file: Path | None = None,
          exclude: list[str] | None = None) -> dict:
    src = src or ROOT / "decks" / "pool-meta"
    out = out or ROOT / "cache" / "pool-meta"
    meta_file = meta_file or ROOT / "data" / "meta-edhtop16.tsv"
    meta = read_meta(meta_file)
    excl = _cmd_key(exclude) if exclude else None
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.dck"):
        old.unlink()
    report = {"ok": [], "problems": [], "unknown_cards": {}, "excluded": []}
    weights = []
    for f in sorted(src.glob("*.txt")):
        deck = parse_text(f.read_text(encoding="utf-8"), name=f.stem)
        key = _cmd_key(deck.commanders)
        if excl and key == excl:
            report["excluded"].append(f.name)
            continue
        fixed = {}
        unknown = []
        for card, n in deck.main.items():
            r = cardnames.resolve(card)
            if r is None:
                unknown.append(card)
                continue
            fixed[r] = fixed.get(r, 0) + n
        deck.main = fixed
        deck.commanders = [cardnames.resolve(c) or c for c in deck.commanders]
        m = meta.get(key)
        deck.name = " + ".join(c.split(",")[0] for c in deck.commanders)
        problems = deck.problems()
        if unknown:
            report["unknown_cards"][f.name] = unknown
            # an unknown card is replaced by a basic land of the deck's colors would distort it; keep the deck only
            # if one or two cards are missing, padded with a Wastes-like colorless land so the count stays 100
            if len(unknown) <= 2:
                deck.main["Wastes"] = deck.main.get("Wastes", 0) + len(unknown)
                problems = deck.problems()
            else:
                problems.append(f"{len(unknown)} cards Forge doesn't know")
        if problems:
            report["problems"].append((f.name, problems))
            continue
        dck = write_dck(deck, out / (f.stem + ".dck"))
        weights.append((dck.name, m["share"] if m else 0.1))
        report["ok"].append(f.name)
    (out / "weights.tsv").write_text(
        "# deck file<TAB>weight (meta share %, EDHTop16 last 6 months)\n"
        + "".join(f"{n}\t{w}\n" for n, w in weights), encoding="utf-8")
    report["out"] = str(out)
    return report
