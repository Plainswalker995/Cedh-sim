"""The trust scorecard, in priority order:

1. Known-answer tests (blocking): obvious swaps must come out right.
2. Combo conversion: when the pilot has a winning line, how often it takes it (puzzles).
3. Meta match: sim results by commander against real tournament data; win turn, draws, win types.
4. Seat effect: how much going first helps, against real events.
5. Games to a verdict: how many paired games a swap test needs for a few points of win rate.
6. Speed: games per hour. Plus Claude usage per batch (an estimate).
"""
from __future__ import annotations

import datetime as dt
import json
import random
from collections import defaultdict
from pathlib import Path

from . import analysis, engine, stats

ROOT = Path(__file__).resolve().parent.parent
MDIR = ROOT / "data" / "metrics"
RUNS = ROOT / "games"
PUZZLES = ROOT / "puzzles"
KNOWN = [
    # name, card out, card in, expected verdict
    ("oracle-for-island", "Thassa's Oracle", "Island", "worse"),
    ("island-for-snow-island", "Island", "Snow-Covered Island", "same"),
]
KNOWN_SEED = 20261114


def _save(name: str, data) -> None:
    MDIR.mkdir(parents=True, exist_ok=True)
    (MDIR / f"{name}.json").write_text(json.dumps(data, indent=1))


def _load(name: str):
    p = MDIR / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def run_known(games: int = 200, jobs: int | None = None) -> list[dict]:
    from .cli import DEFAULT_DECK, ensure_pool, paired_swap, swap_deck
    out = []
    for name, oc, ic, expect in KNOWN:
        variant = swap_deck(DEFAULT_DECK, oc, ic)
        d = RUNS / f"known-{name}-{dt.datetime.now():%Y%m%d-%H%M%S}"
        opts = {"rounds": 10, "slip": 0.0, "nostyles": True, "mc": "on"}
        res = paired_swap(DEFAULT_DECK, variant, ensure_pool(None), d, opts, KNOWN_SEED, games, 0.04, jobs)
        ok = (res["verdict"] == "worse") if expect == "worse" else (res["verdict"] in ("no meaningful difference", "undecided") and res["lo"] < 0 < res["hi"])
        row = {"test": name, "swap": f"{oc} -> {ic}", "expected": expect, "verdict": res["verdict"],
               "change": res["diff"], "lo": res["lo"], "hi": res["hi"], "pairs": res["pairs"], "pass": ok,
               "folder": str(d), "date": dt.date.today().isoformat()}
        out.append(row)
        _save(f"known-{name}", row)
    return out


def run_puzzles(games_each: int = 8, jobs: int | None = None) -> dict:
    from .cli import DEFAULT_DECK, ensure_pool
    results = {}
    for pz in sorted(PUZZLES.glob("*.txt")):
        d = RUNS / f"puzzle-{pz.stem}-{dt.datetime.now():%Y%m%d-%H%M%S}"
        opts = {"rounds": 3, "slip": 0.0, "nostyles": True, "mc": "on", "scenario": pz}
        recs = engine.run_batch(DEFAULT_DECK, ensure_pool(None), games_each, random.randrange(1, 10**9), d,
                                jobs=jobs, opts=opts, quiet=True)
        key = "Thassa's Oracle"
        for line in pz.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("# key:"):
                key = line.split(":", 1)[1].strip()
        conv = sum(1 for r in recs if converted(r))
        tried = sum(1 for r in recs if attempted(r, key))
        results[pz.stem] = {"games": len(recs), "converted": conv, "attempted": tried, "key": key, "folder": str(d)}
    _save("puzzles", {"date": dt.date.today().isoformat(), "results": results})
    return results


def converted(r: dict) -> bool:
    """Won by combo before or during its own first turn."""
    return (r.get("winner") == r.get("hero") and (r.get("winner_turns") or 0) <= 1
            and analysis.win_kind(r.get("how")) == "combo")


def attempted(r: dict, key: str) -> bool:
    """Went for the line in the first round (cast the key card by game turn 4), whether or not it was stopped."""
    hero = r.get("hero")
    for k in r.get("key_plays") or []:
        m = k.split(":", 1)
        if len(m) == 2 and m[0].startswith("T") and m[0][1:].isdigit() and int(m[0][1:]) <= 4 \
                and f"{hero} cast {key}" in k:
            return True
    return converted(r)


def _all_records(kind_filter=("run",)) -> list[dict]:
    recs = []
    for d in sorted(RUNS.glob("run-*")):
        recs += engine.load_results(d)
    return recs


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 4:
        return None
    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def meta_match(recs: list[dict]) -> dict:
    """Every seat plays the same pilot, so every player's result counts toward its commander's sim win rate."""
    games = defaultdict(int)
    wins = defaultdict(int)
    seat_games = defaultdict(int)
    seat_wins = defaultdict(int)
    for r in recs:
        for p, st in (r.get("stats") or {}).items():
            games[p] += 1
            wins[p] += r.get("winner") == p
            s = st.get("seat")
            if s:
                seat_games[s] += 1
                seat_wins[s] += r.get("winner") == p
    share = {}
    wpath = ROOT / "cache" / "pool-meta" / "weights.tsv"
    if wpath.exists():
        from .decks import load_dck
        for line in wpath.read_text().splitlines():
            if line.startswith("#") or "\t" not in line:
                continue
            f, w = line.split("\t")
            dck = ROOT / "cache" / "pool-meta" / f
            if dck.exists():
                share[load_dck(dck).name] = float(w)
    pairs = [(wins[p] / games[p], share[p]) for p in games if p in share and games[p] >= 5]
    rho = _spearman([a for a, _ in pairs], [b for _, b in pairs]) if pairs else None
    win_turns = [r["winner_turns"] for r in recs if r.get("winner")]
    n = len(recs)
    return {"commanders_compared": len(pairs), "rank_correlation_vs_meta_share": rho,
            "avg_win_turn": (sum(win_turns) / len(win_turns)) if win_turns else None,
            "draw_rate": (sum(1 for r in recs if not r.get("winner")) / n) if n else None,
            "win_types": dict(__import__("collections").Counter(analysis.win_kind(r.get("how")) for r in recs)),
            "seat": {s: (seat_wins[s], seat_games[s]) for s in sorted(seat_games)}}


def speed() -> dict | None:
    best = None
    for d in sorted(RUNS.glob("run-*")):
        p = d / "run.json"
        if not p.exists():
            continue
        m = json.loads(p.read_text())
        if not m.get("finished"):
            continue
        t = (dt.datetime.fromisoformat(m["finished"]) - dt.datetime.fromisoformat(m["started"])).total_seconds()
        n = len(engine.load_results(d))
        if t > 0 and n:
            best = {"run": d.name, "games": n, "hours": t / 3600, "games_per_hour": n / (t / 3600)}
    return best


def real_reference() -> dict:
    p = ROOT / "data" / "real-reference.json"
    return json.loads(p.read_text()) if p.exists() else {}


def scorecard(run_known: bool = False, run_puzzles: bool = False, games: int = 200, jobs: int | None = None) -> str:
    if run_puzzles:
        run_puzzles_fn = globals()["run_puzzles"]
        run_puzzles_fn(jobs=jobs)
    if run_known:
        globals()["run_known"](games=games, jobs=jobs)
    ref = real_reference()
    lines = ["cEDH sim trust scorecard", ""]
    # 1
    known = [_load(f"known-{k[0]}") for k in KNOWN]
    if all(known):
        ok = all(k["pass"] for k in known)
        lines.append(f"1. Known-answer tests: {'PASS' if ok else 'FAIL (blocks everything else)'}")
        for k in known:
            lines.append(f"   {k['swap']}: expected {k['expected']}, got {k['verdict']} "
                         f"({k['change']*100:+.1f} points, 95% range {k['lo']*100:+.1f} to {k['hi']*100:+.1f}, "
                         f"{k['pairs']} paired games) -> {'pass' if k['pass'] else 'FAIL'}")
    else:
        lines.append("1. Known-answer tests: not run yet (cedh-sim metrics --run-known)")
    # 2
    pz = _load("puzzles")
    if pz:
        tot = sum(v["games"] for v in pz["results"].values())
        conv = sum(v["converted"] for v in pz["results"].values())
        lines.append(f"2. Combo conversion: {stats.rate_line(conv, tot)}")
        tried = sum(v.get("attempted", 0) for v in pz["results"].values())
        lines.append(f"   Went for the line in the first round: {stats.rate_line(tried, tot)} "
                     "(the gap is mostly opponents' counterspells, as at a real table)")
        for k, v in pz["results"].items():
            lines.append(f"   {k}: won {v['converted']}/{v['games']}, went for it {v.get('attempted', '?')}/{v['games']}")
    else:
        lines.append("2. Combo conversion: not run yet (cedh-sim metrics --run-puzzles)")
    # 3, 4
    recs = _all_records()
    mm = meta_match(recs)
    rho = mm["rank_correlation_vs_meta_share"]
    lines.append(f"3. Meta match ({len(recs)} sim games):")
    lines.append(f"   Rank correlation, sim win rate vs real meta share: "
                 f"{'n/a (need 5+ games per commander)' if rho is None else f'{rho:+.2f}'} over {mm['commanders_compared']} commanders"
                 " (meta share stands in for strength until real win rates are gathered)")
    awt = mm["avg_win_turn"]
    rw = ref.get("avg_win_turn")
    lines.append(f"   Average win turn: {'n/a' if awt is None else f'{awt:.1f}'}"
                 + (f" vs real {rw}" if rw else " (no public turn-by-turn data for real games; see README)"))
    dr = mm["draw_rate"]
    rd = ref.get("draw_rate")
    lines.append(f"   Draw rate: {'n/a' if dr is None else stats.pct(dr)}" + (f" vs real {stats.pct(rd)}" if rd else ""))
    lines.append("   How games end: " + ", ".join(f"{k} {v}" for k, v in sorted(mm["win_types"].items())))
    seat = mm["seat"]
    if seat:
        bits = [f"seat {s}: {stats.pct(w / g) if g else '-'} of {g}" for s, (w, g) in seat.items()]
        rs = ref.get("seat_win_rates")
        lines.append("4. Seat effect: " + ", ".join(bits) + (f" vs real {rs}" if rs else " (real seat data not gathered)"))
    else:
        lines.append("4. Seat effect: no games yet")
    # 5
    swaps = sorted(RUNS.glob("*/swap.json"))
    if swaps:
        s = json.loads(swaps[-1].read_text())
        lines.append(f"5. Games to a verdict: about {s['games_needed_for_min_effect']} paired games to detect "
                     f"{s['min_effect']*100:.0f} points (latest swap test; {s['identical_games']} of {s['pairs']} pairs "
                     "played out the same, which is what makes pairing cheaper)")
    else:
        lines.append("5. Games to a verdict: no swap test yet")
    # 6
    sp = speed()
    if sp:
        lines.append(f"6. Speed: {sp['games_per_hour']:.0f} games per hour ({sp['games']} games in {sp['hours']:.1f} h, {sp['run']})")
    else:
        lines.append("6. Speed: no finished run yet")
    lines.append("   Claude usage: games run as plain code with no Claude in the loop; reading one batch summary "
                 "and writing the summary Doc is roughly 5-10k tokens per batch (estimate).")
    return "\n".join(lines)
