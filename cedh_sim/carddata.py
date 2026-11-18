"""What every card is: type line, mana cost, mana value, colors, color identity, rules text, P/T and loyalty.

Built once from the card scripts of the Forge build the games run on (res/cardsfolder), so the data is
exactly what the engine plays, and cached as cache/card-data.json. `check_scryfall()` compares it with
Scryfall's oracle data (the bulk file "oracle-cards") to find any card whose script differs from the
real card.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import cardnames, config

CACHE = Path(__file__).resolve().parent.parent / "cache" / "card-data.json"
VERSION = 1

SUPERTYPES = {"Basic", "Legendary", "Snow", "World", "Ongoing", "Elite", "Host"}
CARD_TYPES = {"Artifact", "Battle", "Conspiracy", "Creature", "Dungeon", "Enchantment", "Instant", "Kindred",
              "Land", "Phenomenon", "Plane", "Planeswalker", "Scheme", "Sorcery", "Tribal", "Vanguard"}
COLORS = "WUBRG"
COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
# Layouts whose two halves are one card on the battlefield/hand with both faces' costs (split, aftermath ...).
COMBINED_MV = {"Split"}


def parse_types(line: str) -> dict:
    words = line.split()
    sup = [w for w in words if w in SUPERTYPES]
    typ = [w for w in words if w in CARD_TYPES]
    sub = [w for w in words if w not in SUPERTYPES and w not in CARD_TYPES]
    text = " ".join(sup + typ) + (" — " + " ".join(sub) if sub else "")
    return {"type_line": text, "supertypes": sup, "types": typ, "subtypes": sub}


def mana_value(cost: str) -> int:
    """Mana value of a Forge cost string like '2 U U', 'W U' (hybrid WU), '2/B' or 'UP' (Phyrexian)."""
    n = 0
    for part in cost.split():
        if part.isdigit():
            n += int(part)
        elif part in ("X", "Y", "Z", "no", "cost"):
            continue
        elif re.fullmatch(r"2/?[WUBRGC]", part):  # monocolored hybrid ("2B" in Forge, {2/B}) counts 2
            n += 2
        else:
            n += 1
    return n


def cost_symbols(cost: str) -> str:
    """Forge cost as printed symbols: '2 U U' -> '{2}{U}{U}', 'WU' -> '{W/U}', 'UP' -> '{U/P}'."""
    if not cost or cost == "no cost":
        return ""
    out = []
    for part in cost.split():
        if part.isdigit() or part in ("X", "Y", "Z", "C", "S"):
            out.append("{%s}" % part)
        elif part.startswith("2/"):
            out.append("{2/%s}" % part[2:])
        else:
            out.append("{%s}" % "/".join(part))
    return "".join(out)


def _strip_reminder(text: str) -> str:
    return re.sub(r"\([^)]*\)", "", text)


LAND_COLORS = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}


def _identity(faces: list[dict]) -> list[str]:
    """Color identity (rule 903.4): colors of costs, color indicators and mana symbols in rules text."""
    found = set()
    for f in faces:
        found |= set(c for c in f["cost_raw"] if c in COLORS)
        found |= set(f["colors"])
        # basic land types give a mana ability (rule 305.6), so a Triome or shockland has those colors
        found |= {LAND_COLORS[t] for t in f.get("subtypes", []) if t in LAND_COLORS}
        for sym in re.findall(r"\{([^}]+)\}", _strip_reminder(f["oracle"])):
            found |= set(c for c in sym if c in COLORS)
    return [c for c in COLORS if c in found]


def _parse(text: str) -> dict | None:
    faces, cur, layout = [], None, ""
    for line in text.splitlines():
        if line.startswith("AlternateMode:"):
            layout = line.split(":", 1)[1].strip()
            continue
        if line.startswith("ALTERNATE"):
            cur = None
            continue
        if line.startswith("Name:"):
            if cur is None or "name" in cur:
                cur = {}
                faces.append(cur)
            cur["name"] = line[5:].strip()
            continue
        if cur is None:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if key == "ManaCost":
            cur["cost_raw"] = val
        elif key == "Types":
            cur["types_raw"] = val
        elif key == "PT":
            cur["pt"] = val
        elif key == "Loyalty":
            cur["loyalty"] = val
        elif key == "Defense":
            cur["defense"] = val
        elif key == "Colors":
            cur["colors"] = [COLOR_WORDS[w] for w in re.split(r"[ ,]+", val.lower()) if w in COLOR_WORDS]
        elif key == "Oracle" and "oracle" not in cur:
            cur["oracle"] = val.replace("\\n", "\n")
    faces = [f for f in faces if "name" in f]
    if not faces:
        return None
    for f in faces:
        f.setdefault("cost_raw", "")
        f.setdefault("types_raw", "")
        f.setdefault("oracle", "")
        f.setdefault("colors", [])
        f.update(parse_types(f["types_raw"]))
        f["mana_cost"] = cost_symbols(f["cost_raw"])
        f["colors"] = f["colors"] or [c for c in COLORS if c in f["cost_raw"].replace("P", "")]
    front = faces[0]
    mv = sum(mana_value(f["cost_raw"]) for f in faces[:2]) if layout in COMBINED_MV else mana_value(front["cost_raw"])
    rec = {
        "name": " // ".join(f["name"] for f in faces[:2]) if layout in COMBINED_MV else front["name"],
        "layout": layout.lower() or "normal",
        "mana_cost": " // ".join(f["mana_cost"] for f in faces[:2]) if layout in COMBINED_MV else front["mana_cost"],
        "mv": mv,
        "type_line": " // ".join(f["type_line"] for f in faces[:2]) if layout in COMBINED_MV else front["type_line"],
        "supertypes": front["supertypes"],
        "types": sorted({t for f in (faces[:2] if layout in COMBINED_MV else faces[:1]) for t in f["types"]}),
        "subtypes": front["subtypes"],
        "colors": [c for c in COLORS if any(c in f["colors"] for f in (faces[:2] if layout in COMBINED_MV else faces[:1]))],
        "color_identity": _identity(faces),
        "oracle": front["oracle"],
    }
    for k in ("pt", "loyalty", "defense"):
        if k in front:
            rec[k] = front[k]
    if len(faces) > 1:
        rec["faces"] = [{k: f[k] for k in ("name", "mana_cost", "type_line", "oracle") if f.get(k)}
                        | ({"pt": f["pt"]} if "pt" in f else {}) for f in faces]
    return rec


def build() -> dict:
    folder = config.forge_home() / "forge-gui" / "res" / "cardsfolder"
    out: dict[str, dict] = {}
    for f in sorted(folder.rglob("*.txt")):
        try:
            rec = _parse(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if rec:
            out.setdefault(rec["name"], rec)
    return out


_DATA: dict | None = None


def data(rebuild: bool = False) -> dict[str, dict]:
    global _DATA
    if _DATA is None or rebuild:
        cached = None
        if CACHE.exists() and not rebuild:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            if cached.get("version") != VERSION:
                cached = None
        if cached is None:
            cached = {"version": VERSION, "cards": build()}
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cached, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        _DATA = cached["cards"]
    return _DATA


def info(name: str) -> dict | None:
    """The card record for any name Forge knows (any face; accents and case don't matter)."""
    deck_name = cardnames.resolve(name)
    return data().get(deck_name) if deck_name else None


def describe(name: str) -> str:
    c = info(name)
    if not c:
        return f"{name}: not a card Forge knows"
    stats = c.get("pt") or (("loyalty " + c["loyalty"]) if c.get("loyalty") else "")
    head = f"{c['name']}  {c['mana_cost'] or '(no cost)'}  MV {c['mv']}  {c['type_line']}" + (f"  {stats}" if stats else "")
    return head + f"\nIdentity: {''.join(c['color_identity']) or 'colorless'}\n" + c["oracle"]


def shared_types(a: str, b: str) -> set[str]:
    ia, ib = info(a), info(b)
    return set(ia["types"]) & set(ib["types"]) if ia and ib else set()


# ---------------------------------------------------------------- comparison with Scryfall

def _norm(s: str) -> str:
    s = (s or "").replace("’", "'").replace("—", "-").replace("−", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


SELF_RE = re.compile(r"\bthis (creature|artifact|enchantment|land|spell|card|permanent|equipment|vehicle|aura|"
                     r"planeswalker|token|battle|siege|class|saga|room|case|spacecraft|planet|object|source)\b")


def _self_norm(text: str, name: str) -> str:
    """Rules text with every way of naming the card itself made the same: Scryfall's current Oracle says
    "this creature" or a short name ("Zur") where older wording used the full name."""
    t = _norm(text)
    names = {name, name.split(" // ")[0], name.split(",")[0], name.split(" ")[0], name.split(" of ")[0],
             name.split(" the ")[0]}
    for n in sorted({_norm(x) for x in names if len(x) > 2}, key=len, reverse=True):
        t = re.sub(r"(?<![\w'])" + re.escape(n) + r"(?![\w])", "~", t)
    t = SELF_RE.sub("~", t)
    t = re.sub(r"~(?:'s)?(\s*~)+", "~", t)
    # reminder text and punctuation ("[+1]:" vs "+1:") are not rules differences
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"[\[\].,;:\"]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _sf_types(type_line: str) -> list[str]:
    left = type_line.split(" — ")[0]
    return sorted(w for w in left.split() if w in CARD_TYPES)


def check_scryfall(bulk: Path, names: set[str] | None = None) -> list[dict]:
    """Differences between Forge's scripts and Scryfall's oracle data, one dict per card.

    `bulk` is Scryfall's "oracle-cards" bulk file. `names` limits the check (deck names); None checks all.
    """
    sf = {}
    raw = bulk.read_bytes()
    if raw[:2] == b"\x1f\x8b":  # Scryfall serves the bulk file gzipped
        import gzip
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8")
    try:
        cards = json.loads(text)
    except json.JSONDecodeError:  # one card per line (JSON Lines)
        cards = [json.loads(l.rstrip(",")) for l in text.splitlines() if l.strip() not in ("", "[", "]")]
    for c in cards:
        if c.get("layout") in ("token", "double_faced_token", "emblem", "art_series", "vanguard", "scheme",
                               "planar") or c.get("set_type") in ("memorabilia", "token"):
            continue
        sf.setdefault(c["name"], c)
        if "card_faces" in c:
            sf.setdefault(c["card_faces"][0]["name"], c)
    found = data()
    out = []
    for name in sorted(names if names is not None else found):
        rec = found.get(name) or info(name)
        s = sf.get(name) or sf.get(name.split(" // ")[0])
        if rec is None:
            out.append({"card": name, "problem": "Forge has no script for it"})
            continue
        if s is None:
            if names is not None:
                out.append({"card": name, "problem": "not on Scryfall under this name"})
            continue
        diffs = []
        if int(s.get("cmc", 0)) != rec["mv"]:
            diffs.append(f"mana value {rec['mv']} vs real {int(s.get('cmc', 0))}")
        real_types = sorted({t for t in _sf_types(s["type_line"].split(" // ")[0])}) \
            if rec["layout"] not in COMBINED_MV else sorted({t for p in s["type_line"].split(" // ") for t in _sf_types(p)})
        if real_types != rec["types"]:
            diffs.append(f"types {'/'.join(rec['types'])} vs real {'/'.join(real_types)}")
        real_cost = s.get("mana_cost") if "card_faces" not in s or rec["layout"] in COMBINED_MV \
            else s["card_faces"][0].get("mana_cost")
        if real_cost is not None and _norm(real_cost.replace(" ", "")) != _norm(rec["mana_cost"].replace(" ", "")):
            diffs.append(f"cost {rec['mana_cost'] or 'none'} vs real {real_cost or 'none'}")
        real_text = s.get("oracle_text") if "card_faces" not in s else s["card_faces"][0].get("oracle_text", "")
        a, b = _self_norm(rec["oracle"], rec["name"]), _self_norm(real_text, rec["name"])
        if rec["layout"] not in COMBINED_MV and a != b:
            i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
            diffs.append(f"rules text differs: engine '{a[max(0, i - 15):i + 25]}' vs real '{b[max(0, i - 15):i + 25]}'")
        if sorted(s.get("color_identity", [])) != sorted(rec["color_identity"]):
            diffs.append(f"identity {''.join(rec['color_identity']) or 'C'} vs real {''.join(s.get('color_identity', [])) or 'C'}")
        legal = (s.get("legalities") or {}).get("commander")
        if diffs or (names is not None and legal == "banned"):
            out.append({"card": name, "problem": "; ".join(diffs), "commander": legal})
    return out
