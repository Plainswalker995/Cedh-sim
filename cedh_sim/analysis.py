"""Batch summaries, card report, opening-hand stats and loss reasons, from results.jsonl records."""
from __future__ import annotations

from collections import Counter, defaultdict

from .stats import pct, rate_line, wilson

FAST_MANA = {"Mana Crypt", "Sol Ring", "Mana Vault", "Chrome Mox", "Mox Diamond", "Mox Opal", "Mox Amber",
             "Lotus Petal", "Lion's Eye Diamond", "Jeweled Lotus", "Grim Monolith", "Dark Ritual", "Cabal Ritual",
             "Simian Spirit Guide", "Elvish Spirit Guide", "Ancient Tomb", "Gemstone Caverns", "Mox Tantalite",
             "Rite of Flame", "Culling the Weak", "Springleaf Drum", "Arcane Signet", "Talisman of Dominance",
             "Talisman of Creativity", "Talisman of Indulgence", "Talisman of Progress", "Talisman of Hierarchy",
             "Talisman of Conviction", "Fellwar Stone", "Mind Stone", "Basalt Monolith", "Birds of Paradise",
             "Elvish Mystic", "Llanowar Elves", "Fyndhorn Elves", "Delighted Halfling", "Avacyn's Pilgrim"}
STAX = {"Drannith Magistrate", "Rule of Law", "Deafening Silence", "Archon of Emeria", "Grand Abolisher",
        "Cursed Totem", "Damping Sphere", "Null Rod", "Collector Ouphe", "Opposition Agent", "Aven Mindcensor",
        "Notion Thief", "Hullbreacher", "Blind Obedience", "Thalia, Guardian of Thraben", "Lavinia, Azorius Renegade",
        "Silence", "Orim's Chant", "Trinisphere", "Sphere of Resistance", "Thorn of Amethyst", "Esper Sentinel",
        "Rhystic Study", "Mystic Remora", "Smothering Tithe", "Torpor Orb", "Hushbringer", "Linvala, Keeper of Silence"}
COMBO_WINS = ("alt-win", "lose-the-game", "milled", "poison", "infinite")


def hero_stats(r: dict) -> dict:
    return (r.get("stats") or {}).get(r.get("hero")) or {}


def is_draw(r: dict) -> bool:
    return not r.get("winner")


def win_kind(how: str) -> str:
    how = (how or "").lower()
    if "draw" in how:
        return "draw"
    if any(k in how for k in COMBO_WINS):
        return "combo"
    if "commander damage" in how:
        return "commander damage"
    if "damage" in how:
        return "combat/damage"
    return how or "other"


def summary(recs: list[dict]) -> dict:
    hero = recs[0]["hero"] if recs else None
    n = len(recs)
    wins = sum(1 for r in recs if r.get("winner") == hero)
    draws = sum(1 for r in recs if is_draw(r))
    by_seat = defaultdict(lambda: [0, 0])
    for r in recs:
        s = hero_stats(r).get("seat")
        if s:
            by_seat[s][1] += 1
            by_seat[s][0] += r.get("winner") == hero
    win_turns = [r["winner_turns"] for r in recs if r.get("winner")]
    hero_turns = [r["winner_turns"] for r in recs if r.get("winner") == hero]
    kinds = Counter(win_kind(r.get("how")) for r in recs)
    hero_kinds = Counter(win_kind(r.get("how")) for r in recs if r.get("winner") == hero)
    opp_wins = Counter(r["winner"] for r in recs if r.get("winner") and r["winner"] != hero)
    opp_games = Counter(p for r in recs for p in r["players"] if p != hero)
    secs = [r.get("seconds", 0) for r in recs]
    return {
        "hero": hero, "games": n, "wins": wins, "draws": draws,
        "win_rate": wins / n if n else 0, "win_ci": wilson(wins, n), "draw_rate": draws / n if n else 0,
        "by_seat": {s: {"wins": v[0], "games": v[1]} for s, v in sorted(by_seat.items())},
        "avg_win_turn": sum(win_turns) / len(win_turns) if win_turns else None,
        "hero_avg_win_turn": sum(hero_turns) / len(hero_turns) if hero_turns else None,
        "win_types": dict(kinds), "hero_win_types": dict(hero_kinds),
        "opponents": {o: {"games": opp_games[o], "wins": opp_wins.get(o, 0)} for o in opp_games},
        "avg_seconds": sum(secs) / n if n else 0,
    }


def summary_text(s: dict, title: str = "Batch summary") -> str:
    if not s["games"]:
        return f"{title}: no games."
    lines = [f"{title}: {s['hero']}, {s['games']} games",
             f"Win rate: {rate_line(s['wins'], s['games'])} (a fair share in a 4-player pod is 25%)",
             f"Draws: {rate_line(s['draws'], s['games'])}"]
    seat_bits = [f"seat {k}: {v['wins']}/{v['games']}" for k, v in s["by_seat"].items()]
    lines.append("By seat: " + ", ".join(seat_bits))
    if s["hero_avg_win_turn"]:
        lines.append(f"Your average win turn: {s['hero_avg_win_turn']:.1f} (all winners: {s['avg_win_turn']:.1f})")
    lines.append("How games ended: " + ", ".join(f"{k} {v}" for k, v in sorted(s["win_types"].items())))
    if s["hero_win_types"]:
        lines.append("How you won: " + ", ".join(f"{k} {v}" for k, v in sorted(s["hero_win_types"].items())))
    top = sorted(s["opponents"].items(), key=lambda kv: -kv[1]["games"])[:8]
    lines.append("Most-faced opponents: " + ", ".join(f"{o} (won {v['wins']} of {v['games']})" for o, v in top))
    lines.append(f"Average game length: {s['avg_seconds']:.0f} s of compute")
    return "\n".join(lines)


def card_report(recs: list[dict], min_games: int = 5) -> list[dict]:
    """Per card of the hero's deck: games it was seen (drawn), win rate when seen vs not, casts, stuck in hand."""
    hero = recs[0]["hero"] if recs else None
    n = len(recs)
    total_wins = sum(1 for r in recs if r.get("winner") == hero)
    rows = defaultdict(lambda: {"seen": 0, "seen_wins": 0, "cast": 0, "stuck": 0, "in_wins_cast": 0})
    for r in recs:
        hs = hero_stats(r)
        won = r.get("winner") == hero
        seen = set(hs.get("seen") or [])
        cast = Counter(hs.get("cast") or [])
        stuck = set(hs.get("end_hand") or [])
        for c in seen:
            rows[c]["seen"] += 1
            rows[c]["seen_wins"] += won
        for c, k in cast.items():
            rows[c]["cast"] += k
            if won:
                rows[c]["in_wins_cast"] += 1
        for c in stuck:
            rows[c]["stuck"] += 1
    out = []
    for c, v in rows.items():
        if v["seen"] < min_games:
            continue
        not_seen = n - v["seen"]
        wr_seen = v["seen_wins"] / v["seen"]
        wr_not = (total_wins - v["seen_wins"]) / not_seen if not_seen else None
        out.append({"card": c, "seen": v["seen"], "win_when_seen": wr_seen,
                    "win_when_not_seen": wr_not, "delta": (wr_seen - wr_not) if wr_not is not None else None,
                    "cast": v["cast"], "cast_in_wins": v["in_wins_cast"], "dead_in_hand": v["stuck"],
                    "dead_rate": v["stuck"] / v["seen"]})
    out.sort(key=lambda x: -(x["delta"] if x["delta"] is not None else -9))
    return out


def card_report_text(rows: list[dict], n_games: int) -> str:
    if not rows:
        return "Card report: not enough games yet."
    lines = [f"Card report ({n_games} games; a card needs 5+ games seen to be listed; read loosely under ~500 games)",
             "Card | seen | win% when drawn | win% when not | cast in wins | dead in hand"]
    def fmt(r):
        wn = pct(r["win_when_not_seen"]) if r["win_when_not_seen"] is not None else "-"
        return (f"{r['card']} | {r['seen']} | {pct(r['win_when_seen'])} | {wn} | {r['cast_in_wins']} | "
                f"{r['dead_in_hand']} ({pct(r['dead_rate'])})")
    lines.append("Best when drawn:")
    lines += ["  " + fmt(r) for r in rows[:10]]
    lines.append("Worst when drawn:")
    lines += ["  " + fmt(r) for r in rows[-10:]]
    dead = sorted(rows, key=lambda r: -r["dead_rate"])[:10]
    lines.append("Most often stuck in hand at game end:")
    lines += ["  " + fmt(r) for r in dead]
    return "\n".join(lines)


def hand_stats(recs: list[dict]) -> dict:
    n = len(recs)
    mulls = Counter(hero_stats(r).get("mulligans", 0) for r in recs)
    kept7 = mulls.get(0, 0) + mulls.get(1, 0)  # the first mulligan is free in multiplayer
    fast = sum(1 for r in recs if FAST_MANA & set(hero_stats(r).get("opening_hand") or []))
    hero = recs[0]["hero"] if recs else None
    t3 = sum(1 for r in recs if r.get("winner") == hero and (r.get("winner_turns") or 99) <= 3)
    t4 = sum(1 for r in recs if r.get("winner") == hero and (r.get("winner_turns") or 99) <= 4)
    return {"games": n, "mulligans": dict(mulls), "kept_seven": kept7, "fast_mana_in_opener": fast,
            "won_by_turn3": t3, "won_by_turn4": t4}


def hand_stats_text(h: dict) -> str:
    n = h["games"]
    if not n:
        return "Opening hands: no games."
    m = ", ".join(f"{k} mulligan{'s' if k != 1 else ''}: {v}" for k, v in sorted(h["mulligans"].items()))
    return "\n".join([
        f"Opening hands ({n} games): {m}",
        f"Kept a 7-card hand (first mulligan is free): {rate_line(h['kept_seven'], n)}",
        f"Fast mana in the opening hand: {rate_line(h['fast_mana_in_opener'], n)}",
        f"Won by your turn 3: {rate_line(h['won_by_turn3'], n)}; by turn 4: {rate_line(h['won_by_turn4'], n)}"])


def loss_tags(r: dict) -> list[str]:
    hero = r.get("hero")
    if r.get("winner") == hero:
        return []
    if is_draw(r):
        return ["draw"]
    tags = []
    kind = win_kind(r.get("how"))
    tags.append("comboed out" if kind == "combo" else "beaten down" if "damage" in kind else "out-raced")
    hs = hero_stats(r)
    if len(hs.get("countered") or []) >= 2:
        tags.append("countered")
    opp_board = set()
    for p, st in (r.get("stats") or {}).items():
        if p != hero:
            opp_board |= set(st.get("battlefield") or [])
    opp_casts = set()
    for p, st in (r.get("stats") or {}).items():
        if p != hero:
            opp_casts |= set(st.get("cast") or [])
    if (opp_board | opp_casts) & STAX and len(hs.get("cast") or []) <= 6:
        tags.append("stax-locked")
    lands = hs.get("lands") or 0
    if (len(lands) if isinstance(lands, list) else lands) <= 2 or len(hs.get("cast") or []) <= 3:
        tags.append("stumbled")
    if (r.get("winner_turns") or 99) <= 4:
        tags.append("out-raced (fast win)")
    return tags


def loss_text(recs: list[dict]) -> str:
    hero = recs[0]["hero"] if recs else None
    losses = [r for r in recs if r.get("winner") != hero]
    if not losses:
        return "Losses: none."
    c = Counter(t for r in losses for t in loss_tags(r))
    by = Counter(r["winner"] for r in losses if r.get("winner"))
    return ("Why you lost (" + str(len(losses)) + " games, a game can have several tags): "
            + ", ".join(f"{k} {v}" for k, v in c.most_common())
            + "\nWho beat you: " + ", ".join(f"{k} {v}" for k, v in by.most_common(8)))
