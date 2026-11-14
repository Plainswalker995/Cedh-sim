# Changelog

## 0.1.0 (unreleased)

- Four-player Commander games on the Forge engine, headless, in parallel batches, with random seats and a
  fresh seed per game (kept for replays).
- cEDH pilot on every seat: Monte Carlo search with hidden cards re-dealt (no peeking), fast mana and
  commanders deployed early, Thassa's Oracle with Demonic Consultation or Tainted Pact (including tutoring for
  the missing half), the Underworld Breach + Lion's Eye Diamond + Brain Freeze loop.
- Natural variation: three play styles dealt per seat and a configurable slip rate (default 3%).
- Free first mulligan then London; optional learned mulligan model with versions and a promotion gate.
- Round cap: games past it are draws.
- Combo puzzles: first-turn win conversion went from 7 of 32 to 22 of 32 (Tainted Pact held for the Oracle's
  trigger, tutors fetch the missing half, Brain Freeze held for Breach, Lion's Eye Diamond cracked to keep the
  Breach loop going, loop pieces kept out of escape costs). The Breach puzzle alone went from 0 of 8 to 5 of 6.
- Commands: run, auto, swap (paired, early stopping), report, replay, log-game, refresh-pool, metrics, train,
  check.
- Trust scorecard: known-answer tests, combo-conversion puzzles, meta match, seat effect, games to a verdict,
  speed.
- Windows, macOS and Linux launchers and setup scripts; CI build and smoke test on all three.
