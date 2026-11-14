"""One-off repair: batches played before 0.4 recorded seats in sign-up order, not turn order.
Reads the real turn order from each game's play-by-play and rewrites the seats in results.jsonl."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def turn_order(md: Path, n: int) -> list[str]:
    order = []
    for m in re.finditer(r"^### Turn \d+ \((.+)\)$", md.read_text(encoding="utf-8"), re.M):
        if m.group(1) not in order:
            order.append(m.group(1))
        if len(order) == n:
            break
    return order


def fix(run: Path) -> int:
    p = run / "results.jsonl"
    if not p.exists():
        return 0
    out, changed = [], 0
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        md = run / (r.get("file") or "")
        st = r.get("stats") or {}
        if md.is_file() and st and not r.get("seats_fixed"):
            order = turn_order(md, len(st))
            if sorted(order) == sorted(st):
                for name in st:
                    st[name]["seat"] = order.index(name) + 1
                r["players"] = order
                changed += 1
            r["seats_fixed"] = True
        out.append(json.dumps(r))
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed


if __name__ == "__main__":
    runs = [Path(a) for a in sys.argv[1:]] or sorted((ROOT / "games").glob("*/"))
    print(sum(fix(r) for r in runs), "games fixed")
