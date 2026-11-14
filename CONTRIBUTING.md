# Contributing

Issues and pull requests are welcome.

- **Python side** (`cedh_sim/`): standard library only, except `numpy` for the learning layer. Use `pathlib`
  for paths and no shell commands, so everything runs on Windows, macOS and Linux. Run
  `python -m unittest discover -s tests` before sending a change.
- **Forge side**: change a Forge checkout made by `scripts/setup.sh`, then refresh the patch with
  `python3 tools/export_repo.py forge .`. Keep changes inside the cEDH layer where possible, so the patch
  applies cleanly to newer Forge versions.
- **Accuracy changes**: run `cedh-sim metrics --run-known --run-puzzles` before and after, and include both
  scorecards in the pull request. A change that fails a known-answer test isn't merged.
- **Data**: don't commit decklists, tournament results or anything taken from other sites or videos.
  Users import their own data. Keep the Fan Content notice in the README.
- Add a line to `CHANGELOG.md` for anything a user would notice.
