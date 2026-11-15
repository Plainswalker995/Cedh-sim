"""Why a game ended in a draw: an AI mistake (a bug to fix) or a natural stall (as at a real table).

Read from the end of the game: what each player still held, what was on the battlefield, what was countered.
- AI mistake: a player ended the game holding a finished winning combo, or held three or more proactive cards
  (threats, engines, tutors; not counters, removal or rituals) with five or more mana sources in play.
- Natural: a stax piece held the table, the interaction traded off, or everyone ran out of cards.
The signals are deliberately simple; the play-by-play shows the detail.
"""
from __future__ import annotations

import re
from collections import Counter


# a finished win: every card of one group in hand or on the battlefield (one card from each set)
WIN_LINES = [
    ("Thassa's Oracle + Consultation or Pact", [{"Thassa's Oracle"}, {"Demonic Consultation", "Tainted Pact"}]),
    ("Underworld Breach + Lion's Eye Diamond + Brain Freeze",
     [{"Underworld Breach"}, {"Lion's Eye Diamond"}, {"Brain Freeze"}]),
    ("Isochron Scepter + Dramatic Reversal", [{"Isochron Scepter"}, {"Dramatic Reversal"}]),
    ("Kinnan + Basalt Monolith", [{"Kinnan, Bonder Prodigy"}, {"Basalt Monolith"}]),
    ("Dualcaster Mage + Twinflame", [{"Dualcaster Mage"}, {"Twinflame", "Heat Shimmer"}]),
    ("Heliod + Walking Ballista", [{"Heliod, Sun-Crowned"}, {"Walking Ballista"}]),
    ("Doomsday + Thassa's Oracle", [{"Doomsday"}, {"Thassa's Oracle"}]),
]
# cards that lock a table (taxes like Rhystic Study slow it, they don't lock it)
LOCKS = {"Drannith Magistrate", "Rule of Law", "Deafening Silence", "Archon of Emeria", "Collector Ouphe", "Null Rod",
         "Damping Sphere", "Trinisphere", "Blood Moon", "Magus of the Moon", "Cursed Totem", "Hushbringer",
         "Torpor Orb", "Winter Orb", "Stasis", "Tangle Wire", "Root Maze", "Kataki, War's Wage", "Stony Silence",
         "Linvala, Keeper of Silence", "Hushwing Gryff", "Sphere of Resistance", "Thorn of Amethyst",
         "Lavinia, Azorius Renegade", "Grafdigger's Cage", "Opposition", "Static Orb", "Gaddock Teeg",
         "Ethersworn Canonist", "Silence"}
RITUALS = {"Dark Ritual", "Cabal Ritual", "Culling the Weak", "Rite of Flame", "Simian Spirit Guide",
           "Elvish Spirit Guide", "Lotus Petal", "Mox Diamond", "Chrome Mox", "Infernal Plunge", "Sacrifice",
           "Songs of the Damned", "Seething Song", "Jeska's Will"}
# held on purpose: combo pieces waiting for their partner, and answers that are cast on someone else's turn
HELD_ON_PURPOSE = {"Brain Freeze", "Lion's Eye Diamond", "Demonic Consultation", "Tainted Pact", "Thassa's Oracle",
                   "Underworld Breach", "Mindbreak Trap", "Misdirection", "Redirect Lightning", "Deflecting Swat",
                   "Pact of Negation", "Silence", "Orim's Chant", "Borne Upon a Wind", "Veil of Summer",
                   "Deadly Rollick", "Snapback", "Gitaxian Probe", "Mental Misstep",
                   # answers to someone else's spell, and a win-turn card
                   "Commandeer", "Flare of Duplication", "Reiterate", "Return the Favor", "Reverberate", "Fork", "Final Fortune", "Twinflame", "Heat Shimmer"}
PROACTIVE_HELD = 3
MANA_IN_PLAY = 5


def _cards(st: dict, key: str) -> set[str]:
    # battlefield names were split at commas in older records ("Kraum", "Ludevic's Opus"): rejoin pairs
    items = list(st.get(key) or [])
    out = set(items)
    for a, b in zip(items, items[1:]):
        out.add(f"{a}, {b}")
    return out


def _mana_in_play(st: dict, roles: dict) -> int:
    return sum(1 for c in st.get("battlefield") or [] if set(roles.get(c, [])) & {"land", "fast"})


def cause(r: dict, roles: dict | None = None) -> dict | None:
    """None for a game someone won. Otherwise {"kind": "AI mistake" | "natural", "why": [...]}."""
    if r.get("winner"):
        return None
    how = r.get("how") or ""
    if "error" in how:
        return {"kind": "engine error", "why": [r.get("error") or "engine error"]}
    roles = roles or {}
    stats = r.get("stats") or {}
    mistakes, natural = [], []
    for p, st in stats.items():
        if st.get("loss"):
            continue
        hand_cards = _cards(st, "end_hand")
        have = hand_cards | _cards(st, "battlefield")
        for name, groups in WIN_LINES:
            # the Oracle wins only as it enters: it has to be in hand, not already in play
            if all(g & (hand_cards if "Thassa's Oracle" in g else have) for g in groups):
                mistakes.append(f"{p} ended holding {name}")
        mana = _mana_in_play(st, roles) if roles else 0
        # holding counters and removal is normal cEDH play; holding threats, engines and tutors with mana to spare is not
        proactive = [c for c in st.get("end_hand") or []
                     if roles and not set(roles.get(c, [])) & {"land", "interaction", "combo"}
                     and c not in RITUALS and c not in HELD_ON_PURPOSE]
        if len(proactive) >= PROACTIVE_HELD and mana >= MANA_IN_PLAY:
            mistakes.append(f"{p} held {len(proactive)} proactive cards ({', '.join(proactive[:3])}) "
                            f"with {mana} mana sources in play")
    board = set()
    for st in stats.values():
        board |= _cards(st, "battlefield")
    stax = sorted(board & LOCKS)
    if stax:
        natural.append("stax held the table (" + ", ".join(stax[:3]) + ")")
    countered = sum(len(st.get("countered") or []) for st in stats.values())
    if countered >= 4:
        natural.append(f"interaction traded off ({countered} spells countered)")
    alive = [st for st in stats.values() if not st.get("loss")]
    if alive and all(len(st.get("end_hand") or []) <= 2 for st in alive):
        natural.append("everyone ran out of cards")
    if "time limit" in how:
        natural.append("time limit")
    if mistakes:
        return {"kind": "AI mistake", "why": mistakes + natural}
    return {"kind": "natural", "why": natural or ["slow game, no clear mistake found"]}


def roles_for(recs: list[dict]) -> dict:
    names = set()
    for r in recs:
        for st in (r.get("stats") or {}).values():
            names |= set(st.get("battlefield") or []) | set(st.get("end_hand") or [])
    try:
        from .learn import card_roles
        return card_roles(names)
    except Exception:  # card data unavailable: judge without mana counts
        return {}


def text(recs: list[dict]) -> str:
    draws = [r for r in recs if not r.get("winner")]
    if not draws:
        return "Draws: none."
    roles = roles_for(draws)
    causes = [(r, cause(r, roles)) for r in draws]
    kinds = Counter(c["kind"] for _, c in causes)
    lines = [f"Why games were drawn ({len(draws)} draws): " + ", ".join(f"{k} {v}" for k, v in kinds.most_common())
             + " (AI mistakes are bugs to fix; natural draws are compared with real events)"]
    def signal(w: str) -> str:
        if " proactive cards " in w:
            return "a player held threats or engines with mana to spare"
        if " ended holding " in w:
            return "a player held a finished combo: " + w.split(" ended holding ")[1]
        return w.split(" (")[0]
    why = Counter(signal(w) for _, c in causes for w in c["why"])
    lines.append("  Signals: " + ", ".join(f"{k} {v}" for k, v in why.most_common(8)))
    for r, c in causes:
        if c["kind"] == "AI mistake":
            lines.append(f"  game {r['game']}: " + "; ".join(c["why"][:2]))
    return "\n".join(lines)


def tag_file(md_path, c: dict) -> None:
    """Add the draw cause under the result in a game's play-by-play."""
    try:
        t = md_path.read_text(encoding="utf-8")
    except OSError:
        return
    if "**Draw cause:**" in t:
        return
    line = f"- **Draw cause:** {c['kind']}: " + "; ".join(c["why"])
    t = re.sub(r"^(- \*\*How:\*\*.*)$", lambda m: m.group(1) + "\n" + line, t, count=1, flags=re.M)
    md_path.write_text(t, encoding="utf-8")
