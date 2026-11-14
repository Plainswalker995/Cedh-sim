"""Maintainer tool: refresh forge-patch/ from a working Forge checkout and copy the publishable files to a repo folder.

  python3 tools/export_repo.py FORGE_CHECKOUT REPO_DIR

Only the files listed in PUBLISH are copied. Personal and scraped material (config.json, decks/, data/,
games/, cache/, models/) is never copied, whatever is in the source folder.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLISH = ["cedh_sim", "puzzles", "examples", "scripts", "tests", "tools", "forge-patch", ".github",
           "README.md", "LICENSE", "NOTICE.md", "CHANGELOG.md", "CONTRIBUTING.md", ".gitignore", ".gitattributes",
           "cedh-sim", "cedh-sim.ps1", "cedh-sim.cmd", "requirements.txt"]
NEVER = {"config.json", "decks", "data", "games", "cache", "models", "__pycache__"}


def make_patch(forge: Path) -> None:
    git = ["git", "-C", str(forge)]
    commit = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    new = subprocess.check_output(git + ["ls-files", "--others", "--exclude-standard"], text=True).split()
    if new:
        subprocess.check_call(git + ["add", "-N", "--"] + new)
    patch = subprocess.check_output(git + ["diff", "--binary", "HEAD"], text=True)
    out = ROOT / "forge-patch"
    out.mkdir(exist_ok=True)
    (out / "cedh.patch").write_text(patch, encoding="utf-8", newline="\n")
    (out / "FORGE_COMMIT").write_text(commit + "\n", encoding="utf-8")
    files = subprocess.check_output(git + ["diff", "--stat", "HEAD"], text=True)
    (out / "FILES.txt").write_text(files, encoding="utf-8")


def export(repo: Path) -> None:
    for name in PUBLISH:
        src = ROOT / name
        if not src.exists():
            continue
        dst = repo / name
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=lambda d, names: [n for n in names if n in NEVER])
        else:
            shutil.copy2(src, dst)


if __name__ == "__main__":
    make_patch(Path(sys.argv[1]))
    export(Path(sys.argv[2]))
