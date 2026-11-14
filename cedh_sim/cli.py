"""cedh-sim: simulate cEDH games with your deck against the current meta.

  cedh-sim run 120                    play 120 games with your deck (set in config.json)
  cedh-sim run 120 --deck list.txt    another deck: exported list, .dck, or Moxfield link
  cedh-sim run 40 --opponents kinnan,sisay,rog-thras   pin the three opponents
  cedh-sim swap --out "Island" --in "Snapback"         paired swap test, stops when the answer is clear
  cedh-sim report [RUN]               card report, opening hands, loss reasons for a run (default: latest)
  cedh-sim replay RUN GAME [--step]   replay one game from its seed, turn by turn
  cedh-sim metrics                    the trust scorecard
  cedh-sim log-game "..."             record one of your real games as data
  cedh-sim refresh-pool               rebuild the opponent pool from decks/pool-meta and the meta shares
  cedh-sim train [--status]           retrain the mulligan model; promote it only if it does better
  cedh-sim check                      check Python, Java and the Forge build
  cedh-sim auto 120                   Moxfield read, batch, summaries, Doc text, retrain when due
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import sys
from pathlib import Path

from . import analysis, engine, pool, stats
from .decks import load_any, write_dck

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "games"
from . import config

DEFAULT_DECK = config.path("deck", ROOT / "decks" / "my-deck.dck")
MOXFIELD_DECK = config.get("moxfield")
POOL_DIR = ROOT / "cache" / "pool-meta"


def hero_commanders() -> list[str]:
    """Your commanders, left out of the opponent pool so no pod repeats them."""
    from .decks import load_dck
    try:
        return list(load_dck(DEFAULT_DECK).commanders) if DEFAULT_DECK.suffix == ".dck" and DEFAULT_DECK.exists() else []
    except Exception:
        return []


def _now() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def prepare_deck(spec: str | None, name: str | None = None) -> Path:
    if not spec:
        return DEFAULT_DECK
    p = Path(spec).expanduser()
    if p.suffix.lower() == ".dck" and p.exists():
        return p
    deck = load_any(spec, name=name, cache_dir=ROOT / "cache")
    problems = deck.problems()
    from . import cardnames
    unknown = [c for c in list(deck.main) + deck.commanders if cardnames.resolve(c) is None]
    if unknown:
        problems.append("cards Forge doesn't know: " + ", ".join(unknown))
    if problems:
        raise SystemExit("Deck problems: " + "; ".join(problems))
    deck.main = {cardnames.resolve(c): n for c, n in deck.main.items()}
    slug = re.sub(r"[^a-z0-9]+", "-", deck.name.lower()).strip("-") or "deck"
    return write_dck(deck, ROOT / "cache" / "decks" / f"{slug}.dck")


def ensure_pool(opponents: str | None) -> Path:
    if not (POOL_DIR / "weights.tsv").exists():
        pool.build(src=config.path("pool_source", ROOT / "decks" / "pool-meta"), meta_file=config.path("meta_file", ROOT / "data" / "meta.tsv"), exclude=hero_commanders())
    if not opponents:
        return POOL_DIR
    picks = [o.strip().lower() for o in opponents.split(",") if o.strip()]
    pinned = ROOT / "cache" / "pinned" / "-".join(picks)
    pinned.mkdir(parents=True, exist_ok=True)
    for old in pinned.glob("*.dck"):
        old.unlink()
    files = sorted(POOL_DIR.glob("*.dck"))
    for pk in picks:
        hit = [f for f in files if pk in f.stem.lower()]
        if not hit:
            raise SystemExit(f"No pool deck matches '{pk}'. Pool: " + ", ".join(f.stem for f in files))
        (pinned / hit[0].name).write_bytes(hit[0].read_bytes())
    return pinned


def run_opts(a) -> dict:
    return {"rounds": a.rounds, "slip": 0.0 if a.pure else a.slip, "nostyles": a.pure, "mc": a.mc}


def cmd_run(a) -> None:
    err = engine.check_engine()
    if err:
        raise SystemExit(err)
    hero = prepare_deck(a.deck)
    pdir = ensure_pool(a.opponents)
    seed = a.seed if a.seed is not None else random.randrange(1, 10**9)
    out = Path(a.out) if a.out else RUNS / f"run-{_now()}"
    out.mkdir(parents=True, exist_ok=True)
    meta = {"kind": "run", "deck": str(hero), "pool": str(pdir), "seed": seed, "games": a.games,
            "opts": run_opts(a), "started": dt.datetime.now().isoformat(timespec="seconds")}
    (out / "run.json").write_text(json.dumps(meta, indent=1))
    print(f"Playing {a.games} games, seed {seed}, {engine.default_jobs() if not a.jobs else a.jobs} at a time -> {out}")
    recs = engine.run_batch(hero, pdir, a.games, seed, out, jobs=a.jobs, opts=run_opts(a), quiet=a.quiet)
    write_summary(out, recs, meta)


def fresh_deck() -> tuple[Path, str]:
    """Your Moxfield list, read fresh if Moxfield answers; otherwise the saved copy."""
    from . import moxfield
    if not MOXFIELD_DECK:
        return DEFAULT_DECK, "no Moxfield link in config.json; used your saved deck"
    try:
        deck = moxfield.fetch_deck(MOXFIELD_DECK, cache_dir=None)
        from . import cardnames
        unknown = [c for c in list(deck.main) + deck.commanders if cardnames.resolve(c) is None]
        if deck.problems() or unknown:
            return DEFAULT_DECK, "Moxfield list read but has problems; used the saved copy"
        deck.main = {cardnames.resolve(c): n for c, n in deck.main.items()}
        return write_dck(deck, ROOT / "cache" / "decks" / "moxfield-latest.dck"), "read fresh from Moxfield"
    except Exception as e:  # Moxfield blocks automated reads from here most of the time
        return DEFAULT_DECK, f"Moxfield didn't answer ({type(e).__name__}); used the saved copy of your list"


def doc_text(out: Path, recs: list[dict], meta: dict, deck_note: str) -> str:
    """The short batch summary that goes into the one Google Doc per batch."""
    s = analysis.summary(recs)
    lines = [f"cEDH sim batch {out.name}", "",
             f"Deck: {Path(meta['deck']).stem} ({deck_note})",
             f"Games: {s['games']}; win rate {stats.rate_line(s['wins'], s['games'])}; draws {stats.rate_line(s['draws'], s['games'])}",
             "By seat: " + ", ".join(f"seat {k}: {v['wins']}/{v['games']}" for k, v in s["by_seat"].items()),
             analysis.hand_stats_text(analysis.hand_stats(recs)).splitlines()[1],
             analysis.loss_text(recs).splitlines()[0], "",
             "Game recaps:"]
    lines += ["  " + engine.one_line(r) for r in recs]
    lines += ["", f"Full play-by-play files: {out / 'games'}", f"Full summary and card report: {out / 'summary.md'}"]
    return "\n".join(lines)


def cmd_auto(a) -> None:
    """Moxfield read, batch, summaries, Doc text, then retrain when enough new hands have come in."""
    from . import learn
    err = engine.check_engine()
    if err:
        raise SystemExit(err)
    hero, note = (prepare_deck(a.deck), "the list you gave") if a.deck else fresh_deck()
    pdir = ensure_pool(None)
    seed = random.randrange(1, 10**9)
    out = RUNS / f"run-{_now()}"
    out.mkdir(parents=True, exist_ok=True)
    meta = {"kind": "run", "deck": str(hero), "pool": str(pdir), "seed": seed, "games": a.games,
            "opts": run_opts(a), "started": dt.datetime.now().isoformat(timespec="seconds"), "deck_note": note}
    (out / "run.json").write_text(json.dumps(meta, indent=1))
    recs = engine.run_batch(hero, pdir, a.games, seed, out, jobs=a.jobs, opts=run_opts(a), quiet=True)
    write_summary(out, recs, meta)
    (out / "doc.md").write_text(doc_text(out, recs, meta, note), encoding="utf-8")
    state_p = ROOT / "models" / "auto-state.json"
    state = json.loads(state_p.read_text()) if state_p.exists() else {"hands_at_last_train": 0}
    hands = len(learn.examples())
    if hands - state["hands_at_last_train"] >= a.retrain_every:
        print("\n" + learn.train_and_maybe_promote(jobs=a.jobs))
        state["hands_at_last_train"] = hands
        state_p.parent.mkdir(parents=True, exist_ok=True)
        state_p.write_text(json.dumps(state))
    else:
        print(f"\nLearning: {hands - state['hands_at_last_train']} new hands since the last retrain "
              f"(retrains at {a.retrain_every}).")
    print(f"Doc text: {out / 'doc.md'}")


def write_summary(out: Path, recs: list[dict], meta: dict) -> str:
    s = analysis.summary(recs)
    text = "\n\n".join([analysis.summary_text(s), analysis.hand_stats_text(analysis.hand_stats(recs)),
                        analysis.loss_text(recs),
                        analysis.card_report_text(analysis.card_report(recs), len(recs))])
    recaps = "\n".join(engine.one_line(r) for r in recs)
    settings = (f"Settings: seed {meta['seed']}, round cap {meta['opts'].get('rounds')} turns each, "
                f"slip rate {meta['opts'].get('slip')}, play styles {'off' if meta['opts'].get('nostyles') else 'on'}, "
                f"pool {Path(meta['pool']).name}")
    full = f"{text}\n\n{settings}\n\nGames:\n{recaps}\n"
    (out / "summary.md").write_text(full, encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(s, indent=1, default=list))
    meta["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    (out / "run.json").write_text(json.dumps(meta, indent=1))
    print("\n" + analysis.summary_text(s))
    print(f"\nFull summary: {out / 'summary.md'}")
    return full


def latest_run() -> Path:
    runs = sorted(p for p in RUNS.glob("run-*") if (p / "results.jsonl").exists())
    if not runs:
        raise SystemExit("No runs yet.")
    return runs[-1]


def cmd_report(a) -> None:
    out = Path(a.run) if a.run else latest_run()
    if not out.exists():
        out = RUNS / a.run
    recs = engine.load_results(out)
    meta = json.loads((out / "run.json").read_text()) if (out / "run.json").exists() else {"seed": "?", "opts": {}, "pool": "?"}
    print(write_summary(out, recs, meta))


def swap_deck(base: Path, out_card: str, in_card: str) -> Path:
    from . import cardnames
    from .decks import load_dck
    d = load_dck(base)
    oc, ic = cardnames.resolve(out_card), cardnames.resolve(in_card)
    if ic is None:
        raise SystemExit(f"Forge doesn't know '{in_card}'.")
    if oc not in d.main:
        raise SystemExit(f"'{out_card}' is not in the deck.")
    d.main[oc] -= 1
    if d.main[oc] <= 0:
        del d.main[oc]
    d.main[ic] = d.main.get(ic, 0) + 1
    d.name = d.name  # same player name, so the reports line up
    slug = re.sub(r"[^a-z0-9]+", "-", f"{base.stem} {oc} to {ic}".lower()).strip("-")
    return write_dck(d, ROOT / "cache" / "decks" / f"{slug}.dck")


def paired_swap(base: Path, variant: Path, pdir: Path, out: Path, opts: dict, seed: int, max_games: int,
                min_effect: float, jobs: int | None, chunk: int | None = None, quiet: bool = True) -> dict:
    """Same games (seed, game number: pod, seats, shuffles) with both lists; stop once the answer is clear."""
    jobs = jobs or engine.default_jobs()
    chunk = chunk or max(jobs * 2, 8)
    a_dir, b_dir = out / "before", out / "after"
    done, verdict = 0, None
    while done < max_games:
        n = min(chunk, max_games - done)
        engine.run_batch(base, pdir, n, seed, a_dir, jobs=jobs, start=done + 1, opts=opts, quiet=quiet)
        engine.run_batch(variant, pdir, n, seed, b_dir, jobs=jobs, start=done + 1, opts=opts, quiet=quiet)
        done += n
        res = swap_result(engine.load_results(a_dir), engine.load_results(b_dir), min_effect)
        print(f"after {res['pairs']} paired games: change {res['diff']*100:+.1f} points "
              f"(95% range {res['lo']*100:+.1f} to {res['hi']*100:+.1f})", flush=True)
        if res["pairs"] >= 2 * chunk and res["verdict"] != "undecided":
            verdict = res
            break
        verdict = res
    (out / "swap.json").write_text(json.dumps(verdict, indent=1))
    return verdict


def swap_result(a: list[dict], b: list[dict], min_effect: float) -> dict:
    ga = {r["game"]: r for r in a}
    gb = {r["game"]: r for r in b}
    diffs = []
    for g in sorted(set(ga) & set(gb)):
        ra, rb = ga[g], gb[g]
        diffs.append(float(rb.get("winner") == rb.get("hero")) - float(ra.get("winner") == ra.get("hero")))
    m, lo, hi = stats.paired(diffs)
    if lo > 0:
        v = "better"
    elif hi < 0:
        v = "worse"
    elif lo > -min_effect and hi < min_effect:
        v = "no meaningful difference"
    else:
        v = "undecided"
    var = stats.variance(diffs)
    wa = sum(1 for r in a if r.get("winner") == r.get("hero"))
    wb = sum(1 for r in b if r.get("winner") == r.get("hero"))
    return {"pairs": len(diffs), "diff": m, "lo": lo, "hi": hi, "verdict": v,
            "before": [wa, len(a)], "after": [wb, len(b)],
            "games_needed_for_min_effect": stats.games_needed(var, min_effect), "min_effect": min_effect,
            "identical_games": sum(1 for d in diffs if d == 0)}


def swap_text(res: dict, out_card: str, in_card: str) -> str:
    v = {"better": f"{in_card} wins more than {out_card}",
         "worse": f"{in_card} wins less than {out_card}",
         "no meaningful difference": f"no difference bigger than {res['min_effect']*100:.0f} points",
         "undecided": "within noise: not enough games to tell"}[res["verdict"]]
    return (f"Swap {out_card} -> {in_card}: {v}.\n"
            f"Before: {stats.rate_line(*res['before'])}\nAfter: {stats.rate_line(*res['after'])}\n"
            f"Paired change: {res['diff']*100:+.1f} points (95% range {res['lo']*100:+.1f} to {res['hi']*100:+.1f}) "
            f"over {res['pairs']} paired games.\n"
            f"Games needed to detect {res['min_effect']*100:.0f} points at this noise: about "
            f"{res['games_needed_for_min_effect']} pairs.")


def cmd_swap(a) -> None:
    base = prepare_deck(a.deck)
    variant = swap_deck(base, a.out_card, a.in_card)
    pdir = ensure_pool(a.opponents)
    seed = a.seed if a.seed is not None else random.randrange(1, 10**9)
    out = RUNS / f"swap-{_now()}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps({"kind": "swap", "deck": str(base), "variant": str(variant),
                                              "seed": seed, "opts": run_opts(a), "pool": str(pdir)}, indent=1))
    res = paired_swap(base, variant, pdir, out, run_opts(a), seed, a.games, a.min_effect / 100, a.jobs)
    text = swap_text(res, a.out_card, a.in_card)
    (out / "summary.md").write_text(text + "\n")
    print("\n" + text)


def cmd_replay(a) -> None:
    out = Path(a.run) if Path(a.run).exists() else RUNS / a.run
    meta = json.loads((out / "run.json").read_text())
    rdir = out / f"replay-{a.game}"
    deck = Path(meta.get("deck"))
    opts = dict(meta.get("opts", {}))
    if (rdir / "results.jsonl").exists():
        (rdir / "results.jsonl").unlink()
    engine.run_batch(deck, Path(meta["pool"]), 1, meta["seed"], rdir, jobs=1, start=a.game, opts=opts, quiet=True)
    md = sorted((rdir / "games").glob("*.md"))
    if not md:
        raise SystemExit("Replay failed; see " + str(rdir))
    text = md[-1].read_text(encoding="utf-8")
    if not a.step:
        print(text)
        print(f"\n(Saved as {md[-1]}. The pod, seats, shuffles and styles come from the seed; the AI's search has a "
              "time budget, so a replay can differ from the original in small ways.)")
        return
    parts = re.split(r"(?m)^### ", text)
    print(parts[0])
    for part in parts[1:]:
        print("### " + part)
        try:
            input("-- Enter for the next turn, Ctrl-C to stop --")
        except (EOFError, KeyboardInterrupt):
            break


def cmd_log_game(a) -> None:
    from . import realdata
    rec = realdata.log_my_game(a.text, deck=a.deck_name, seat=a.seat, result=a.result, turn=a.turn, how=a.how,
                               opponents=a.opponents)
    print("Logged: " + json.dumps(rec))


def cmd_refresh_pool(a) -> None:
    src = Path(a.from_dir).expanduser() if a.from_dir else config.path("pool_source", ROOT / "decks" / "pool-meta")
    meta = Path(a.meta).expanduser() if a.meta else config.path("meta_file", ROOT / "data" / "meta.tsv")
    if not src.is_dir() or not any(src.glob("*.txt")):
        raise SystemExit(f"No deck lists (*.txt) in {src}. Export the opponent lists you want as text files there "
                         "(one deck per file, with a 'Commander:' line), or pass --from FOLDER.")
    r = pool.build(src=src, meta_file=meta, exclude=hero_commanders())
    print(f"Pool rebuilt: {len(r['ok'])} decks in {r['out']}")
    if r["problems"]:
        print("Left out: " + "; ".join(f"{f}: {', '.join(p)}" for f, p in r["problems"]))
    if r["unknown_cards"]:
        print("Cards Forge doesn't know (replaced by Wastes when 1-2): "
              + "; ".join(f"{f}: {', '.join(c)}" for f, c in r["unknown_cards"].items()))


def cmd_check(a) -> None:
    """Setup check: Python, Java, the patched Forge build and the card list."""
    import shutil
    print(f"Python {sys.version.split()[0]}")
    print("Java: " + ("found" if shutil.which("java") else "MISSING (install a JDK 17 or newer)"))
    err = engine.check_engine()
    print("Forge engine: " + (err or f"built ({engine.JAR.name})"))
    if not err:
        from . import cardnames
        print(f"Cards Forge knows: {len(cardnames.index())}")
    if err or not shutil.which("java"):
        raise SystemExit(1)


def cmd_metrics(a) -> None:
    from . import metrics
    print(metrics.scorecard(run_known=a.run_known, run_puzzles=a.run_puzzles, games=a.games, jobs=a.jobs))


def cmd_train(a) -> None:
    from . import learn
    if a.status:
        print(learn.status())
        return
    print(learn.train_and_maybe_promote(games=a.games, jobs=a.jobs, force=a.force, min_examples=a.min_examples))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="cedh-sim", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--deck", help="your deck: exported list (.txt), .dck or Moxfield link (default: the deck in config.json)")
        p.add_argument("--opponents", help="pin opponents: comma-separated pool names, e.g. kinnan,sisay,rog-thras")
        p.add_argument("--seed", type=int, help="base seed (default: a fresh random one, saved for replays)")
        p.add_argument("--jobs", type=int, help="games at once (default: about half the cores)")
        p.add_argument("--rounds", type=int, default=10, help="turns each before the game is a draw (default 10)")
        p.add_argument("--slip", type=float, default=0.03, help="human-like slip rate (default 0.03)")
        p.add_argument("--pure", action="store_true", help="pure-strength test: no slips, same balanced style at every seat")
        p.add_argument("--mc", default="on", choices=["on", "off", "max"], help="search strength (default on)")
        p.add_argument("--quiet", action="store_true")

    p = sub.add_parser("run", help="play a batch")
    p.add_argument("games", type=int)
    p.add_argument("--out")
    common(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("swap", help="paired swap test")
    p.add_argument("--out", dest="out_card", required=True)
    p.add_argument("--in", dest="in_card", required=True)
    p.add_argument("--games", type=int, default=400, help="most paired games (default 400)")
    p.add_argument("--min-effect", type=float, default=4.0, help="smallest change worth knowing, in points (default 4)")
    common(p)
    p.set_defaults(func=cmd_swap)

    p = sub.add_parser("auto", help="Moxfield read, batch, summaries, Doc text, retrain when due")
    p.add_argument("games", type=int, nargs="?", default=120)
    p.add_argument("--retrain-every", type=int, default=800, help="new opening hands between retrains (default 800)")
    common(p)
    p.set_defaults(func=cmd_auto)

    p = sub.add_parser("report")
    p.add_argument("run", nargs="?")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("replay")
    p.add_argument("run")
    p.add_argument("game", type=int)
    p.add_argument("--step", action="store_true")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("log-game")
    p.add_argument("text", nargs="?", default="")
    p.add_argument("--deck-name")
    p.add_argument("--seat", type=int)
    p.add_argument("--result", choices=["win", "loss", "draw"])
    p.add_argument("--turn", type=int)
    p.add_argument("--how")
    p.add_argument("--opponents")
    p.set_defaults(func=cmd_log_game)

    p = sub.add_parser("refresh-pool", help="rebuild the opponent pool from a folder of exported lists")
    p.add_argument("--from", dest="from_dir", help="folder of deck lists, one .txt per deck (default: config pool_source)")
    p.add_argument("--meta", help="optional tab-separated meta shares: rank, commanders, entries, meta_share")
    p.set_defaults(func=cmd_refresh_pool)

    p = sub.add_parser("check", help="check the setup")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("metrics")
    p.add_argument("--run-known", action="store_true", help="also run the known-answer swap tests (slow)")
    p.add_argument("--run-puzzles", action="store_true", help="also run the combo puzzles")
    p.add_argument("--games", type=int, default=200)
    p.add_argument("--jobs", type=int)
    p.set_defaults(func=cmd_metrics)

    p = sub.add_parser("train", help="retrain the mulligan model; promote only if it does better on fixed seeds")
    p.add_argument("--force", action="store_true", help="promote even if it did not do better")
    p.add_argument("--status", action="store_true", help="show the model in use and the version history")
    p.add_argument("--games", type=int, default=120, help="paired games to judge a new version (default 120)")
    p.add_argument("--min-examples", type=int, default=400, help="hands needed before training (default 400)")
    p.add_argument("--jobs", type=int)
    p.set_defaults(func=cmd_train)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main(sys.argv[1:])
