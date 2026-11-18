"""The learning layer: training data from every game played, a learned mulligan model, versions and a promotion gate.

What it learns today: keep or ship an opening hand. Every seat of every game is a training example
(the kept hand, how many mulligans, and whether that player won). A small logistic model turns a hand
into a chance to win; the pilot keeps a hand when that chance beats what a mulligan is worth.

How a new version gets in: it is trained, saved as models/vN.properties, then played against the
current version on a fixed set of seeds with only your seat using the model (paired games, same pods,
same shuffles). It becomes models/current.properties only if your win rate is not worse with it and the
known-answer tests still pass. Everything is recorded in models/history.json.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
from pathlib import Path

import numpy as np

from . import analysis, cardnames, engine, stats

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
RUNS = ROOT / "games"
ROLES_CACHE = ROOT / "cache" / "card-roles.json"
EVAL_SEED = 777001
FEATURES = ["lands", "lands2", "fast", "tutor", "interaction", "combo", "draw", "size", "mana_ok"]
COMBO_NAMES = {"Thassa's Oracle", "Demonic Consultation", "Tainted Pact", "Underworld Breach", "Lion's Eye Diamond",
               "Brain Freeze", "Laboratory Maniac", "Jace, Wielder of Mysteries", "Dramatic Reversal", "Isochron Scepter",
               "Hermit Druid", "Kiki-Jiki, Mirror Breaker", "Splinter Twin", "Food Chain", "Helm of the Host",
               "Ad Nauseam", "Doomsday", "Necrotic Ooze", "Walking Ballista", "Heliod, Sun-Crowned", "Displacer Kitten",
               "Basalt Monolith", "Dockside Extortionist", "Bolas's Citadel", "Aetherflux Reservoir", "Grinding Station",
               "Sensei's Divining Top", "Timetwister", "Peer into the Abyss", "Razaketh, the Foulblooded",
               "Thoracle", "Exquisite Blood", "Sanguine Bond", "Niv-Mizzet, Parun", "Curiosity", "Tandem Lookout",
               "Ophidian Eye", "Dualcaster Mage", "Twinflame", "Ghostly Flicker", "Mystic Sanctuary"}
INTERACTION_NAMES = {"Silence", "Orim's Chant", "Pyroblast", "Red Elemental Blast", "Mental Misstep",
                     "Swan Song", "Snapback", "Chain of Vapor", "Cyclonic Rift", "Abrupt Decay", "Assassin's Trophy",
                     "Deflecting Swat", "Grand Abolisher", "Drannith Magistrate", "Opposition Agent"}


# ---------------------------------------------------------------- card roles

ROLES_VERSION = 3
STAX_RE = re.compile(r"can't cast|can't search|can't draw more than|costs? \{\d\} more|don't untap|"
                     r"can't be activated|can't untap|enter(s)? (the battlefield )?tapped|can't cause|"
                     r"each player can't|opponents can't|players can't|skip (their|your) untap", re.I)
PROTECT_RE = re.compile(r"can't be countered|spells you control can't|hexproof|indestructible|"
                        r"phase(s)? out|your opponents can't cast spells|can't be the targets?", re.I)


def classify(info: dict) -> list[str]:
    """cEDH roles from a card's type line, mana value and rules text (a carddata record)."""
    name, types, mv = info["name"], set(info["types"]), info["mv"]
    oracle = re.sub(r"\([^)]*\)", "", info["oracle"]).lower()
    if "Land" in types and not types & {"Creature", "Artifact"}:
        return ["land"]
    roles = []
    makes_mana = bool(re.search(r"\badd \{|\badd (one|two|three|x) mana|\badd mana", oracle))
    if name in analysis.FAST_MANA or ("Artifact" in types and "Creature" not in types and makes_mana and mv <= 2) \
            or (types & {"Instant", "Sorcery"} and makes_mana and mv <= 1):
        roles.append("fast")
    elif (makes_mana or re.search(r"untap target (land|forest)|additional land|create (a|two|three|x) treasure", oracle)) and mv <= 4 \
            and "Land" not in types:
        roles.append("ramp")
    if re.search(r"search (your|target opponent's|target player's) library for (a|an|any|up to \w+|one|two|three|x) (?!basic)(?![\w ,-]*land card)", oracle) \
            and "land" not in re.split(r"library for", oracle, maxsplit=1)[1][:40]:
        roles.append("tutor")
    if name in INTERACTION_NAMES or re.search(r"counter target|destroy target|exile target|"
                                              r"return target [^.]* to its owner's hand|exile any number of target|"
                                              r"deals? \d+ damage to (any|target)|target (nonland )?permanent|"
                                              r"each opponent sacrifices|destroy all|exile all|"
                                              r"target player [^.]*discards|target opponent [^.]*discards", oracle):
        roles.append("interaction")
    if name in COMBO_NAMES or "win the game" in oracle:
        roles.append("combo")
    if re.search(r"\bdraws? (a|an additional|two|three|four|five|six|seven|x|that many) cards?|\bdraw cards\b|"
                 r"look at the top|put that card into your hand|exile the top [^.]* you may (play|cast)", oracle):
        roles.append("draw")
    if PROTECT_RE.search(oracle) and "target creature you don't control" not in oracle:
        roles.append("protection")
    if re.search(r"from (a|your|their|its owner's) graveyard (on)?to the battlefield|enchanted creature card to the battlefield|"
                 r"return (target|up to \w+ target) [^.]*card[^.]* from your graveyard to (your hand|the battlefield)|"
                 r"you may (cast|play) [^.]* from your graveyard", oracle):
        roles.append("recursion")
    if re.search(r"\bsacrifice (a|an|another) (creature|artifact|permanent)\b[^.]*:|"
                 r"whenever [^.]* dies, [^.]*(each opponent|target player|target opponent)|"
                 r"spells? (you cast )?costs? \{\d\} less|untap (all|target|another|each)|"
                 r"copy target (instant|sorcery|activated)|you may cast spells as though|create a token that's a copy|"
                 r"whenever you cast (a|an|your) [^.]*spell", oracle):
        roles.append("engine")
    if STAX_RE.search(oracle) and types & {"Artifact", "Enchantment", "Creature", "Planeswalker"}:
        roles.append("stax")
    return roles


def card_roles(names: set[str]) -> dict[str, list[str]]:
    """Roles for these cards, from the cache of every card's roles (rebuilt when the card data or rules change)."""
    from . import carddata
    cache = json.loads(ROLES_CACHE.read_text()) if ROLES_CACHE.exists() else {}
    if cache.get("_version") != ROLES_VERSION or len(cache) < 1000:
        cache = {n: classify(rec) for n, rec in carddata.data().items()}
        cache["_version"] = ROLES_VERSION
        ROLES_CACHE.parent.mkdir(parents=True, exist_ok=True)
        ROLES_CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))
    out = {}
    for n in names:
        key = cardnames.resolve(n) or n
        out[n] = cache.get(key) or cache.get(key.split(" // ")[0]) or []
    return out


# ---------------------------------------------------------------- data

def training_runs() -> list[Path]:
    """Real game batches: normal runs, swap tests and known-answer tests. Puzzles are set-up positions, so they are left out."""
    out = []
    for d in sorted(RUNS.iterdir()) if RUNS.exists() else []:
        if d.name.startswith("puzzle-"):
            continue
        for rj in d.rglob("results.jsonl"):
            out.append(rj.parent)
    return out


def examples(runs: list[Path] | None = None) -> list[dict]:
    rows = []
    for d in runs or training_runs():
        for r in engine.load_results(d):
            if r.get("error") or r.get("timed_out"):
                continue
            for p, st in (r.get("stats") or {}).items():
                hand = st.get("opening_hand")
                if not hand:
                    continue
                m = st.get("mulligans", 0) or 0
                rows.append({"hand": hand, "size": 7 - max(0, m - 1), "won": int(r.get("winner") == p),
                             "draw": int(not r.get("winner")), "player": p})
    return rows


def featurize(rows: list[dict], roles: dict[str, list[str]]) -> np.ndarray:
    X = []
    for r in rows:
        c = {k: 0 for k in ("land", "fast", "tutor", "interaction", "combo", "draw")}
        for n in r["hand"]:
            for role in roles.get(n, []):
                if role in c:  # the mulligan model reads these six; newer roles are for reports
                    c[role] += 1
        mana = c["land"] + c["fast"]
        X.append([c["land"], c["land"] ** 2, c["fast"], c["tutor"], c["interaction"], c["combo"], c["draw"],
                  r["size"], 1 if 3 <= mana <= 5 else 0])
    return np.array(X, dtype=float)


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0, steps: int = 3000, lr: float = 0.05):
    """Plain logistic regression with an L2 penalty, by gradient descent on standardized features."""
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = (X - mu) / sd
    w = np.zeros(Z.shape[1])
    b = np.log(max(y.mean(), 1e-3) / max(1 - y.mean(), 1e-3))
    n = len(y)
    for _ in range(steps):
        p = 1 / (1 + np.exp(-(Z @ w + b)))
        g = p - y
        w -= lr * (Z.T @ g / n + l2 * w / n)
        b -= lr * g.mean()
    # back to raw feature units, which is what the pilot computes
    w_raw = w / sd
    b_raw = b - float((w * mu / sd).sum())
    return b_raw, w_raw


def log_loss(X, y, b, w) -> float:
    p = np.clip(1 / (1 + np.exp(-(X @ w + b))), 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def train(min_examples: int = 400) -> dict:
    rows = examples()
    if len(rows) < min_examples:
        return {"ok": False, "reason": f"only {len(rows)} hands to learn from; need {min_examples} (play more games first)",
                "examples": len(rows)}
    names = {n for r in rows for n in r["hand"]}
    roles = card_roles(names)
    X = featurize(rows, roles)
    y = np.array([r["won"] for r in rows], dtype=float)
    rng = np.random.default_rng(0)
    idx = rng.permutation(len(y))
    cut = int(len(y) * 0.8)
    tr, te = idx[:cut], idx[cut:]
    b, w = fit_logistic(X[tr], y[tr])
    held = log_loss(X[te], y[te], b, w)
    base = log_loss(X[te], y[te], float(np.log(y[tr].mean() / (1 - y[tr].mean()))), np.zeros_like(w))
    b, w = fit_logistic(X, y)  # final fit on everything
    expect = {}
    for size in range(1, 8):
        k = [i for i, r in enumerate(rows) if r["size"] == size]
        if k:
            wins = sum(rows[i]["won"] for i in k)
            expect[size] = (wins + 0.25 * 8) / (len(k) + 8)  # shrunk toward a fair 25%
        else:
            expect[size] = 0.25 * (0.85 ** (7 - size))
    by_role = {}
    for n, rs in roles.items():
        for role in rs if isinstance(rs, list) else []:
            if role != "land":
                by_role.setdefault(role, set()).add(n.split(" // ")[0])
    from . import decide
    return {"ok": True, "examples": len(rows), "bias": b, "w": dict(zip(FEATURES, map(float, w))),
            "expect": expect, "cards": {k: sorted(v) for k, v in by_role.items()},
            "held_out_log_loss": held, "baseline_log_loss": base,
            "decisions": decide.train_all()}


def write_properties(model: dict, path: Path, version: str) -> None:
    lines = [f"# cEDH sim mulligan model {version}, trained {dt.datetime.now():%Y-%m-%d %H:%M} on {model['examples']} hands",
             f"version={version}", f"bias={model['bias']:.6f}"]
    lines += [f"w.{k}={v:.6f}" for k, v in model["w"].items()]
    lines += [f"expect.{k}={v:.4f}" for k, v in sorted(model["expect"].items())]
    lines.append("min_keep=5")
    for role in ("fast", "tutor", "interaction", "combo", "draw"):
        cards = [c.replace("\\", "") for c in model["cards"].get(role, [])]
        lines.append(f"cards.{role}=" + "|".join(cards))
    from . import decide
    lines += decide.properties_lines(model.get("decisions") or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- versions and promotion

def history() -> list[dict]:
    p = MODELS / "history.json"
    return json.loads(p.read_text()) if p.exists() else []


def _save_history(h: list[dict]) -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    (MODELS / "history.json").write_text(json.dumps(h, indent=1))


def next_version() -> str:
    nums = [int(m.group(1)) for p in MODELS.glob("v*.properties") if (m := re.match(r"v(\d+)$", p.stem))]
    return f"v{max(nums, default=0) + 1}"


def evaluate(candidate: Path, incumbent: Path | None, games: int, jobs: int | None, hero: Path, pool: Path) -> dict:
    """Paired games on fixed seeds: your seat uses the candidate, then the incumbent (or Forge's own mulligan rule)."""
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = RUNS / f"train-eval-{stamp}"
    opts = {"rounds": 10, "slip": 0.0, "nostyles": True, "mc": "on", "modelhero": True}
    a = engine.run_batch(hero, pool, games, EVAL_SEED, base / "candidate", jobs=jobs,
                         opts={**opts, "model": str(candidate)}, quiet=True)
    b = engine.run_batch(hero, pool, games, EVAL_SEED, base / "incumbent", jobs=jobs,
                         opts={**opts, "model": str(incumbent) if incumbent else "none"}, quiet=True)
    bw = {r["game"]: int(r.get("winner") == r["hero"]) for r in b}
    pairs = [(int(r.get("winner") == r["hero"]), bw[r["game"]]) for r in a if r["game"] in bw]
    diff, lo, hi = stats.paired([x - y for x, y in pairs])
    return {"folder": str(base), "pairs": len(pairs), "diff": diff, "lo": lo, "hi": hi,
            "candidate_wins": sum(x for x, _ in pairs), "incumbent_wins": sum(y for _, y in pairs)}


def train_and_maybe_promote(games: int = 120, jobs: int | None = None, force: bool = False,
                            min_examples: int = 400) -> str:
    from .cli import DEFAULT_DECK, ensure_pool
    from . import metrics
    model = train(min_examples=min_examples)
    if not model["ok"]:
        return "Training skipped: " + model["reason"]
    ver = next_version()
    path = MODELS / f"{ver}.properties"
    write_properties(model, path, ver)
    current = MODELS / "current.properties"
    lines = [f"Trained mulligan model {ver} on {model['examples']} hands "
             f"(held-out log loss {model['held_out_log_loss']:.4f} vs {model['baseline_log_loss']:.4f} for no model; lower is better)."]
    top = sorted(model["w"].items(), key=lambda kv: -abs(kv[1]))[:4]
    lines.append("Strongest signals per card in hand: " + ", ".join(f"{k} {v:+.2f}" for k, v in top))
    from . import decide
    lines += ["In-game decisions:"] + ["  " + x for x in decide.summary(model.get("decisions") or {})]
    known = [metrics._load(f"known-{k[0]}") for k in metrics.KNOWN]
    known_ok = all(known) and all(k["pass"] for k in known)
    ev = evaluate(path, current if current.exists() else None, games, jobs, DEFAULT_DECK, ensure_pool(None))
    vs = "current model" if current.exists() else "Forge's built-in mulligan rule"
    lines.append(f"Against the {vs} over {ev['pairs']} paired games on fixed seeds (your seat only): "
                 f"{ev['candidate_wins']} wins vs {ev['incumbent_wins']}, change {ev['diff']*100:+.1f} points "
                 f"(95% range {ev['lo']*100:+.1f} to {ev['hi']*100:+.1f}).")
    promote = force or (known_ok and ev["diff"] > 0 and ev["lo"] > -0.03)
    if not known_ok and not force:
        lines.append("Not promoted: the known-answer tests have not passed yet (run cedh-sim metrics --run-known).")
    elif promote:
        shutil.copyfile(path, current)
        lines.append(f"Promoted: {ver} is now the model every seat uses.")
    else:
        lines.append(f"Kept the {vs}: {ver} did not clearly do better.")
    h = history()
    h.append({"version": ver, "date": dt.datetime.now().isoformat(timespec="seconds"), "examples": model["examples"],
              "held_out_log_loss": model["held_out_log_loss"], "baseline_log_loss": model["baseline_log_loss"],
              "decisions": {k: {kk: v.get(kk) for kk in ("ok", "examples", "held_out_log_loss", "baseline_log_loss",
                                                          "policy_option1")} for k, v in
                            (model.get("decisions") or {}).items()},
              "eval": ev, "known_ok": known_ok, "promoted": bool(promote)})
    _save_history(h)
    return "\n".join(lines)


def status() -> str:
    h = history()
    cur = MODELS / "current.properties"
    head = cur.read_text().splitlines()[0] if cur.exists() else "No learned model in use yet (Forge's own mulligan rule)."
    rows = examples()
    from . import decide
    ex = decide.examples(decide.decision_runs())
    lines = [head, f"Training data on hand: {len(rows)} opening hands from {len(training_runs())} batches; "
             + ", ".join(f"{len(ex.get(k, []))} {k} decisions" for k in decide.KINDS) + "."]
    for e in h[-5:]:
        lines.append(f"{e['version']} ({e['date'][:10]}): {e['examples']} hands, change "
                     f"{e['eval']['diff']*100:+.1f} points over {e['eval']['pairs']} games, "
                     f"{'promoted' if e['promoted'] else 'not promoted'}")
    return "\n".join(lines)
