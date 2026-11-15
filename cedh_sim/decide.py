"""Learned in-game decisions: when to go for the win, whether to tutor for protection first, when to counter.

The pilot writes every such decision to the game's journal with its features (see Decisions.java):
    DECIDE <kind> <option 0|1> <rule|model|explore> f1=v,f2=v | <player>
Each kind gets a small logistic model of the chance that this player goes on to win, from the features, the option
taken, and option x feature terms. The pilot then takes the option with the higher predicted chance. A kind is only
learned once there are enough examples of both options; until then the hand-written rule decides.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from . import engine

KINDS = {
    "go": "cast the winning line now (1) or wait a turn (0)",
    "shield": "with the win in hand, tutor for protection first (1) or not (0)",
    "counter": "counter an opponent's spell (1) or keep the counterspell (0)",
}
# examples needed per kind, and of each option, before the model replaces the rule
MINIMUM = {"counter": (300, 40), "go": (150, 30), "shield": (150, 30)}
# set-up positions (puzzles) put a win on the table every game: good data for the go and shield choices
FROM_PUZZLES = {"go", "shield"}
LINE = re.compile(r"DECIDE (\w+) ([01]) (\w+) (.*?) \| (.+)$")


def parse(line: str) -> dict | None:
    m = LINE.search(line)
    if not m:
        return None
    feats = {}
    for kv in m.group(4).split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            try:
                feats[k.strip()] = float(v)
            except ValueError:
                pass
    return {"kind": m.group(1), "choice": int(m.group(2)), "why": m.group(3), "f": feats, "player": m.group(5).strip()}


def examples(runs: list[Path]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for d in runs:
        puzzle = any(part.startswith("puzzle-") for part in d.parts)
        for r in engine.load_results(d):
            if r.get("error") or r.get("timed_out"):
                continue
            for line in r.get("journal") or []:
                e = parse(line)
                if e and (not puzzle or e["kind"] in FROM_PUZZLES):
                    e["won"] = int(r.get("winner") == e["player"])
                    out.setdefault(e["kind"], []).append(e)
    return out


def _matrix(rows: list[dict], names: list[str]) -> np.ndarray:
    X = []
    for r in rows:
        f = [r["f"].get(n, 0.0) for n in names]
        c = r["choice"]
        X.append(f + [c] + [c * v for v in f])
    return np.array(X, dtype=float)


def fit(kind: str, rows: list[dict]) -> dict:
    from .learn import fit_logistic, log_loss
    ones = sum(r["choice"] for r in rows)
    need, each = MINIMUM.get(kind, (300, 40))
    if len(rows) < need or min(ones, len(rows) - ones) < each:
        return {"ok": False, "kind": kind, "examples": len(rows), "option1": ones,
                "reason": f"{len(rows)} examples, {ones} of option 1 and {len(rows) - ones} of option 0 "
                          f"(needs {need}, with {each} of each)"}
    names = sorted({k for r in rows for k in r["f"]})
    X = _matrix(rows, names)
    y = np.array([r["won"] for r in rows], dtype=float)
    idx = np.random.default_rng(1).permutation(len(y))
    cut = int(len(y) * 0.8)
    tr, te = idx[:cut], idx[cut:]
    b, w = fit_logistic(X[tr], y[tr], l2=4.0)  # strong penalty: small data, keep the model modest
    held = log_loss(X[te], y[te], b, w)
    p0 = float(np.clip(y[tr].mean(), 1e-3, 1 - 1e-3))
    base = log_loss(X[te], y[te], float(np.log(p0 / (1 - p0))), np.zeros_like(w))
    b, w = fit_logistic(X, y, l2=4.0)
    k = len(names)
    model = {"ok": True, "kind": kind, "examples": len(rows), "option1": ones, "names": names, "bias": float(b),
             "w": dict(zip(names, map(float, w[:k]))), "c": float(w[k]), "cw": dict(zip(names, map(float, w[k + 1:]))),
             "held_out_log_loss": held, "baseline_log_loss": base}
    # how often the learned policy would take option 1 on the situations seen
    z1 = np.array([_score(model, r["f"], 1) for r in rows])
    z0 = np.array([_score(model, r["f"], 0) for r in rows])
    model["policy_option1"] = float((z1 >= z0).mean())
    return model


def _score(model: dict, f: dict, c: int) -> float:
    z = model["bias"] + c * model["c"]
    for n in model["names"]:
        x = f.get(n, 0.0)
        z += model["w"][n] * x + c * model["cw"][n] * x
    return z


def decision_runs() -> list[Path]:
    """Every batch with results, puzzles included (they count for the go and shield choices only)."""
    from .learn import RUNS
    return sorted({rj.parent for rj in RUNS.rglob("results.jsonl")}) if RUNS.exists() else []


def train_all(runs: list[Path] | None = None) -> dict[str, dict]:
    ex = examples(runs if runs is not None else decision_runs())
    return {k: fit(k, ex.get(k, [])) for k in KINDS}


def properties_lines(models: dict[str, dict]) -> list[str]:
    lines = []
    for kind, m in models.items():
        if not m.get("ok"):
            continue
        lines.append(f"# {kind}: {KINDS[kind]}; {m['examples']} examples")
        lines.append(f"{kind}.bias={m['bias']:.6f}")
        lines.append(f"{kind}.c={m['c']:.6f}")
        lines += [f"{kind}.w.{n}={v:.6f}" for n, v in m["w"].items()]
        lines += [f"{kind}.cw.{n}={v:.6f}" for n, v in m["cw"].items()]
    return lines


def summary(models: dict[str, dict]) -> list[str]:
    out = []
    for kind, m in models.items():
        if m.get("ok"):
            out.append(f"{kind} ({KINDS[kind]}): learned from {m['examples']} decisions; held-out log loss "
                       f"{m['held_out_log_loss']:.4f} vs {m['baseline_log_loss']:.4f} for none; picks option 1 in "
                       f"{m['policy_option1']*100:.0f}% of the situations seen")
        else:
            out.append(f"{kind} ({KINDS[kind]}): rule still decides; {m['reason']}")
    return out
