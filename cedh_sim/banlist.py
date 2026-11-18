"""The official Commander banned list and the deck-building rules every deck is checked against.

Source: Wizards of the Coast's banned and restricted page (magic.wizards.com/en/banned-restricted-list),
read 2026-11-18. Latest Commander change on it: Feb 9, 2026 (Lutri, the Spellchaser now banned only as a
companion). The Oct 12, 2026 announcement changed no Commander cards; the next one is due Nov 30, 2026.
Update BANNED and AS_OF when a new announcement lands.
"""
from __future__ import annotations

import re

AS_OF = "2026-11-17 (latest Commander change: Feb 9, 2026)"

BANNED = {
    "Ancestral Recall", "Balance", "Black Lotus", "Chaos Orb", "Channel", "Dockside Extortionist",
    "Emrakul, the Aeons Torn", "Erayo, Soratami Ascendant", "Falling Star", "Fastbond", "Flash",
    "Golos, Tireless Pilgrim", "Griselbrand", "Hullbreacher", "Iona, Shield of Emeria", "Jeweled Lotus", "Karakas",
    "Leovold, Emissary of Trest", "Library of Alexandria", "Limited Resources", "Mana Crypt", "Mox Emerald",
    "Mox Jet", "Mox Pearl", "Mox Ruby", "Mox Sapphire", "Nadu, Winged Wisdom", "Paradox Engine", "Primeval Titan",
    "Prophet of Kruphix", "Recurring Nightmare", "Rofellos, Llanowar Emissary", "Shahrazad", "Sundering Titan",
    "Sylvan Primordial", "Time Vault", "Time Walk", "Tinker", "Tolarian Academy", "Trade Secrets", "Upheaval",
    "Yawgmoth's Bargain",
    # banned in every format for racist or culturally offensive imagery or text
    "Invoke Prejudice", "Cleanse", "Stone-Throwing Devils", "Pradesh Gypsies", "Jihad", "Imprison", "Crusade",
}
BANNED_AS_COMPANION = {"Lutri, the Spellchaser"}

BASICS = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes", "Snow-Covered Plains", "Snow-Covered Island",
          "Snow-Covered Swamp", "Snow-Covered Mountain", "Snow-Covered Forest", "Snow-Covered Wastes"}

PAIRINGS = ("Friends forever", "Doctor's companion", "Choose a Background")


def banned_reason(card: dict) -> str | None:
    """Why a card can't be in a Commander deck, or None."""
    if card["name"] in BANNED:
        return "banned"
    if "Conspiracy" in card["types"]:
        return "Conspiracy cards are banned"
    if re.search(r"\bante\b", card["oracle"], re.I):
        return "ante cards are banned"
    return None


def any_number(card: dict) -> bool:
    o = card["oracle"]
    return card["name"] in BASICS or "A deck can have any number of cards named" in o or \
        bool(re.search(r"A deck can have up to \w+ cards named", o))


def can_command(card: dict) -> bool:
    if "can be your commander" in card["oracle"]:
        return True
    if "Legendary" not in card["supertypes"]:
        return False
    if "Creature" in card["types"]:
        return True
    # legendary Vehicles and Spacecraft with power and toughness (Commander rules update, 2025)
    return bool({"Vehicle", "Spacecraft"} & set(card["subtypes"])) and bool(card.get("pt"))


def _pair_ok(a: dict, b: dict) -> bool:
    oa, ob = a["oracle"], b["oracle"]
    if re.search(rf"Partner with {re.escape(b['name'])}", oa) and re.search(rf"Partner with {re.escape(a['name'])}", ob):
        return True
    plain = re.compile(r"^Partner(?! with)(\s*\(|\s*$)", re.M)
    if plain.search(oa) and plain.search(ob):
        return True
    for va in re.findall(r"^Partner—([^\n(]+)", oa, re.M):
        if va.strip() in [v.strip() for v in re.findall(r"^Partner—([^\n(]+)", ob, re.M)]:
            return True
    if "Friends forever" in oa and "Friends forever" in ob:
        return True
    for x, y in ((a, b), (b, a)):
        if "Choose a Background" in x["oracle"] and "Background" in y["subtypes"]:
            return True
        if "Doctor's companion" in x["oracle"] and {"Time", "Lord", "Doctor"} <= set(y["subtypes"]):
            return True
    return False


def check(commanders: list[str], main: dict[str, int], info) -> list[str]:
    """Rule problems for a deck: banned cards, commanders, color identity and singleton.

    `info` maps a card name to its card-data record (carddata.info). Deck size is checked by Deck.problems().
    """
    out = []
    cmd = [info(c) for c in commanders]
    for name, rec in zip(commanders, cmd):
        if rec is None:
            continue
        if rec["name"] in BANNED:
            out.append(f"{rec['name']} is banned as a commander")
        elif not can_command(rec) and not ("Background" in rec["subtypes"] and
                                           any(o and "Choose a Background" in o["oracle"] for o in cmd)):
            out.append(f"{rec['name']} can't be a commander")
    if len(cmd) > 2:
        out.append("more than two commanders")
    elif len(cmd) == 2 and all(cmd) and not _pair_ok(cmd[0], cmd[1]):
        out.append(f"{cmd[0]['name']} and {cmd[1]['name']} can't be commanders together")
    identity = set().union(*(set(c["color_identity"]) for c in cmd if c))
    for name, n in main.items():
        rec = info(name)
        if rec is None:
            continue
        why = banned_reason(rec)
        if why:
            out.append(f"{rec['name']}: {why}")
        extra = set(rec["color_identity"]) - identity
        if extra and all(cmd):
            out.append(f"{rec['name']} is outside the commanders' colors ({''.join(sorted(extra))})")
        if n > 1 and not any_number(rec):
            out.append(f"{n} copies of {rec['name']} (Commander is singleton)")
    return out
