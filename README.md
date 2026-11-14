# cEDH sim

Simulates four-player competitive EDH (cEDH) games so you can test a deck, and changes to it, against a
field of opponents. Your deck sits in one seat, three opponents are drawn from a pool you supply, turn
order is random and every game gets a fresh shuffle. Games are played under the Commander rules by the
[Forge](https://github.com/Card-Forge/forge) rules engine, with a cEDH-minded AI pilot in every seat.

> Unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy. Not approved or
> endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of
> the Coast LLC. Free and non-commercial; no card images. See [NOTICE.md](NOTICE.md).

## What you get

- **Batches**: `run 120` plays 120 games in parallel and writes each game's play-by-play (summary on top),
  plus a batch summary: win rate with its 95% range, results by seat, win turns, how games ended, opening
  hands, why you lost, and a card report (win rate when a card is drawn vs not, cards stuck in hand).
- **Swap tester**: plays the same games (same pods, seats and shuffles) with and without a change, and stops
  as soon as the answer is clear, so you learn whether a swap helps with far fewer games.
- **Replay** any game from its seed, step by step.
- **A learning layer** that trains on every game played and only adopts a new version when it does better.
- **A trust scorecard** (`metrics`) that tells you how far to trust the numbers.

## Setup

You need **Python 3.10+**, **git**, a **JDK 17 or newer** (21 recommended) and **Maven 3.8+**. The setup
script downloads Forge's source at a fixed commit, applies this project's patch and builds it
(a few minutes the first time).

**macOS** (with [Homebrew](https://brew.sh)):

```sh
brew install python git openjdk@21 maven
git clone <this repo> cedh-sim && cd cedh-sim
bash scripts/setup.sh
```

**Linux** (Debian/Ubuntu):

```sh
sudo apt install python3 git openjdk-21-jdk maven
git clone <this repo> cedh-sim && cd cedh-sim
bash scripts/setup.sh
```

**Windows** (PowerShell, with [winget](https://learn.microsoft.com/windows/package-manager/)):

```powershell
winget install Python.Python.3.12 Git.Git EclipseAdoptium.Temurin.21.JDK Apache.Maven
git clone <this repo> cedh-sim; cd cedh-sim
.\scripts\setup.ps1
```

For the learning layer, also `pip install -r requirements.txt` (numpy). `cedh-sim check` confirms the setup.

## Your deck and the opponent pool

1. **Your deck**: export it from Moxfield (or anywhere) as text, or pass a Moxfield link. Put the path or
   link in `config.json` so you don't have to type it each time:

   ```json
   {"deck": "decks/my-deck.txt", "moxfield": "https://moxfield.com/decks/<id>"}
   ```

   Moxfield often turns away automated reads; when it does, export the list as text instead.
2. **Opponents**: put the lists you want to face in `decks/pool-meta/`, one text file per deck with a
   `Commander:` line (partners as `A + B`). Optionally add `data/meta.tsv` (columns `rank`, `commanders`,
   `entries`, `meta_share`) so popular commanders come up more often. Then `cedh-sim refresh-pool`.
   You gather these lists yourself; follow each site's terms when you do. No lists ship with this project.

`examples/` has throwaway decks (a commander and basic lands) used by the setup check.

## Commands

Run as `sh cedh-sim <command>` (macOS/Linux), `.\cedh-sim.ps1 <command>` (PowerShell), `cedh-sim <command>`
(Command Prompt), or `python -m cedh_sim <command>` anywhere.

| Command | What it does |
|---|---|
| `run 120` | Play a batch. `--deck` for another deck, `--opponents kinnan,sisay,rog` to pin the pod. |
| `auto 120` | Hands-off: tries your Moxfield link, plays, writes the summary, card report and a short summary for sharing (`doc.md`), and retrains when enough new games have come in. Good for a scheduled job. |
| `swap --out "Island" --in "Snapback"` | Paired swap test with early stopping. `--min-effect 4` sets the smallest change worth detecting, in points. |
| `report [RUN]` | Summary, card report, opening hands and loss reasons for a batch (default: latest). |
| `replay RUN GAME [--step]` | Replay one game from its seed. |
| `metrics [--run-known] [--run-puzzles]` | The trust scorecard. |
| `train [--status]` | Retrain the mulligan model; promote it only if it wins more. |
| `log-game "won seat 2 turn 5 by Thassa's Oracle vs Kinnan, Sisay"` | Record a real game of yours as data. |
| `refresh-pool [--from FOLDER] [--meta FILE]` | Rebuild the opponent pool. |
| `check` | Check Python, Java and the Forge build. |

Options for `run`, `auto` and `swap`: `--rounds 10` (turns each before a game is a draw), `--slip 0.03`
(human-like mistakes), `--pure` (no slips, one style everywhere: for strength tests), `--jobs N`, `--seed N`,
`--mc on|off|max` (search strength).

Output lands in `games/run-<time>/`: `games/game-NNN.md` (one per game), `summary.md`, `doc.md`,
`results.jsonl` (one record per game, used for replays and learning).

## How the AI plays

- **The same pilot in every seat**: Forge's AI with Monte Carlo search over candidate plays. When it thinks
  ahead, hidden cards (hands, libraries) are re-dealt at random, so it never peeks.
- **cEDH lines on top**: fast mana and commanders deployed early; Thassa's Oracle with Demonic Consultation
  or Tainted Pact (holding the Consultation for the Oracle's trigger, tutoring for the missing half); the
  Underworld Breach + Lion's Eye Diamond + Brain Freeze loop; plus the combo lines Forge already knows.
- **Mulligans**: the first mulligan is free, then London. A learned model can decide keeps (below).
- **Natural variation**: new seed and shuffle per game, several lists per commander when the pool has them,
  three play styles (patient, balanced, aggressive) dealt per seat, and a small slip rate.
- **Round cap**: games that go past it end as draws and count as draws, as at a tournament. Each draw is
  tagged with its cause: an AI mistake (a finished combo or threats held with mana to spare: a bug to fix) or a
  natural stall (a lock piece, traded-off interaction, empty hands).

## The learning layer

Every seat of every game is training data: the kept hand, the number of mulligans, and whether that player
won. `train` fits a small logistic model of which opening hands win, saves it as `models/vN.properties`,
then plays it against the version in use on a fixed set of seeds, with only your seat using it, as paired
games. It becomes `models/current.properties` only if your win rate doesn't drop and the known-answer tests
pass. History is in `models/history.json`. Today it learns mulligans; the rest of the pilot is search plus
hand-written cEDH lines.

## The trust scorecard

1. **Known-answer tests** (blocking): cutting Thassa's Oracle for an Island must test worse; swapping an
   Island for a Snow-Covered Island must test the same. Needs a deck with Thassa's Oracle.
2. **Combo conversion**: set-up positions (`puzzles/`) where a win is on the table: how often the pilot takes it.
3. **Meta match**: sim win rate by commander against its real meta share, average win turn, draw rate, how
   games end.
4. **Seat effect** against real events, when you supply reference numbers in `data/real-reference.json`.
5. **Games to a verdict** for a swap test.
6. **Speed** in games per hour.

## Limits, honestly

- Forge's AI is a solid player, not a top cEDH pilot. It misses lines a strong human finds, and it is weaker
  at politics and at reading the table. Treat results as a comparison tool (this list against that list,
  same opponents), not as a prediction of your tournament win rate.
- Small samples mislead. Every rate comes with its 95% range; a 4-point difference needs a few hundred
  paired games to show.
- Games run long: in early batches far more games hit the round cap as draws than at real events (roughly 1
  in 5). The scorecard tracks this against real numbers; read win rates with that in mind.
- Speed depends on the machine: roughly 20 games an hour per parallel job with search on (about 60 an hour
  on four cores).
- The opponent pool is only as good as the lists you put in it.

## License

GPL-3.0, like Forge. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
