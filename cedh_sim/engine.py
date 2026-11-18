"""Runs batches of games on the Forge engine, in parallel, and gathers the results.

Each worker is one Java process playing a slice of the game numbers. A game's pod, seats,
shuffles and play styles all come from (base seed, game number), so a game can be replayed
and a swap test plays the same games with both versions of a deck.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from . import config

FORGE_HOME = config.forge_home()
FORGE_CWD = FORGE_HOME / "forge-gui"


def _find_jar() -> Path:
    hits = sorted((FORGE_HOME / "forge-gui-desktop" / "target").glob("forge-gui-desktop-*-jar-with-dependencies.jar"))
    return hits[-1] if hits else FORGE_HOME / "forge-gui-desktop" / "target" / "forge-gui-desktop-jar-with-dependencies.jar"


JAR = _find_jar()


def default_jobs() -> int:
    # each game uses about two cores (game thread plus Monte Carlo rollouts)
    return max(1, (os.cpu_count() or 2) // 2 + 1)


def java_cmd(hero: Path, pool: Path, n: int, seed: int, start: int, out: Path, opts: dict) -> list[str]:
    cmd = ["java", "-Xss16m", f"-Xmx{opts.get('mem', '2g')}", "-jar", str(JAR), "cedh",
           "-hero", str(hero), "-pool", str(pool), "-n", str(n), "-s", str(seed), "-start", str(start),
           "-o", str(out), "-c", str(opts.get("timeout", 900)), "-mc", opts.get("mc", "on"),
           "-rounds", str(opts.get("rounds", 10)), "-slip", str(opts.get("slip", 0.03))]
    if opts.get("nostyles"):
        cmd.append("-nostyles")
    if opts.get("explore"):
        cmd += ["-explore", str(opts["explore"])]
    model = opts.get("model", "current")
    if model:
        mp = Path(model) if Path(model).suffix else ROOT / "models" / f"{model}.properties"
        if mp.exists():
            cmd += ["-model", str(mp)]
            if opts.get("modelhero"):
                cmd.append("-modelhero")
    if opts.get("roles", True):
        from . import learn  # the AI plays ramp, protection, stax, recursion and engine cards by their role
        cmd += ["-roles", str(learn.roles_file())]
    if opts.get("scenario"):
        cmd += ["-scenario", str(opts["scenario"])]
    return cmd


def run_batch(hero: Path, pool: Path, n: int, seed: int, out: Path, jobs: int | None = None,
              start: int = 1, opts: dict | None = None, quiet: bool = False) -> list[dict]:
    """Play games start..start+n-1 and return their result records (also kept in out/results.jsonl)."""
    opts = opts or {}
    out = Path(out).resolve()  # the engine runs in Forge's folder, so a relative path would land there
    hero, pool = Path(hero).resolve(), Path(pool).resolve()
    jobs = max(1, min(jobs or default_jobs(), n))
    out.mkdir(parents=True, exist_ok=True)
    (out / "games").mkdir(exist_ok=True)
    slices, base, extra = [], n // jobs, n % jobs
    s = start
    for j in range(jobs):
        cnt = base + (1 if j < extra else 0)
        if cnt:
            slices.append((s, cnt))
            s += cnt
    procs = []
    for j, (s0, cnt) in enumerate(slices):
        wdir = out / f".worker-{s0}"
        if wdir.exists():
            shutil.rmtree(wdir)
        log = open(out / f".worker-{s0}.log", "w")
        p = subprocess.Popen(java_cmd(hero, pool, cnt, seed, s0, wdir, opts), cwd=FORGE_CWD,
                             stdout=log, stderr=subprocess.STDOUT)
        procs.append((p, wdir, log))
    seen = set()
    results_path = out / "results.jsonl"
    while True:
        alive = [p for p, _, _ in procs if p.poll() is None]
        _collect(procs, out, seen, results_path, quiet)
        if not alive:
            break
        time.sleep(2)
    for _, wdir, log in procs:
        log.close()
        shutil.rmtree(wdir, ignore_errors=True)
    if not opts.get("_retry"):
        # a worker that dies (out of memory in one long game, say) takes the rest of its slice with it:
        # play the missing games once more, one game per fresh worker with more memory, so a game that
        # runs out of memory again loses only itself
        done = {r["game"] for r in load_results(out)}
        missing = [g for g in range(start, start + n) if g not in done]
        for s0, cnt in _ranges(missing):
            if not quiet:
                print(f"replaying games {s0}-{s0 + cnt - 1} after a worker stopped early", flush=True)
            for c0 in range(s0, s0 + cnt, jobs):
                k = min(jobs, s0 + cnt - c0)
                run_batch(hero, pool, k, seed, out, jobs=k, start=c0,
                          opts={**opts, "_retry": True, "mem": "3g"}, quiet=quiet)
        lost = [g for g in missing if g not in {r["game"] for r in load_results(out)}]
        if lost and not quiet:
            print(f"{len(lost)} game(s) could not be played (out of memory twice): {', '.join(map(str, lost))}",
                  flush=True)
    return load_results(out)


def _ranges(games: list[int]) -> list[tuple[int, int]]:
    """Consecutive game numbers as (first, count) runs."""
    out = []
    for g in sorted(games):
        if out and out[-1][0] + out[-1][1] == g:
            out[-1] = (out[-1][0], out[-1][1] + 1)
        else:
            out.append((g, 1))
    return out


def _collect(procs, out: Path, seen: set, results_path: Path, quiet: bool) -> None:
    """Move finished games from the workers into the batch folder as they end."""
    for _, wdir, _ in procs:
        rj = wdir / "results.jsonl"
        if not rj.exists():
            continue
        try:
            text = rj.read_text(encoding="utf-8")
        except OSError:  # a shared or network folder can fail a read now and then: try again on the next pass
            continue
        for line in text.splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # still being written
            if rec["game"] in seen:
                continue
            seen.add(rec["game"])
            src = wdir / rec["file"] if rec.get("file") else None
            if src and src.exists():
                dst = out / "games" / src.name
                try:
                    shutil.copyfile(src, dst)
                    rec["file"] = f"games/{src.name}"
                except OSError:
                    seen.discard(rec["game"])
                    continue
            with open(results_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
            if not quiet:
                print(one_line(rec), flush=True)


def one_line(rec: dict) -> str:
    w = rec.get("winner") or "draw"
    seat = (rec.get("stats", {}).get(rec.get("hero"), {}) or {}).get("seat", "?")
    return (f"game {rec['game']:>4} | seat {seat} | winner: {w} | {rec.get('how')} | "
            f"winner's turn {rec.get('winner_turns')} | {rec.get('seconds')} s")


def load_results(out: Path) -> list[dict]:
    p = out / "results.jsonl"
    if not p.exists():
        return []
    recs = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            recs[r["game"]] = r
        except (json.JSONDecodeError, KeyError):
            pass
    return [recs[k] for k in sorted(recs)]


def check_engine() -> str | None:
    if not JAR.exists():
        return f"Forge engine not built: {JAR} is missing (see README)."
    if shutil.which("java") is None:
        return "Java is not installed."
    return None


if __name__ == "__main__":
    print(check_engine() or "engine ok", file=sys.stderr)
