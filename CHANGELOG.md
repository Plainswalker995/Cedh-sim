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
- Commands: run, auto, swap (paired, early stopping), report, replay, log-game, refresh-pool, metrics, train,
  check.
- Trust scorecard: known-answer tests, combo-conversion puzzles, meta match, seat effect, games to a verdict,
  speed.
- Thassa's Oracle stays in hand as the win condition: cast only when it wins by devotion, the library is
  nearly gone, or Demonic Consultation or Tainted Pact can follow it the same turn.
- Draw causes: every drawn game is tagged in its play-by-play and the batch summary as an AI mistake (a
  player held a finished combo, or held threats, engines or tutors with mana to spare) or a natural stall
  (a lock piece, interaction traded off, everyone out of cards). The scorecard counts both.
- Fix: `--out` with a relative folder wrote games into Forge's folder.
- Cheap draw engines (Mystic Remora, Rhystic Study, Esper Sentinel, Necropotence and the like) are deployed early,
  after fast mana and before the commanders, instead of sitting in hand.
- Mulligans: after the free first mulligan, a seven is judged against the six it would become, so decent sevens
  are kept.
- Fix: the loss-reason report crashed on newer game records.
- Fix: seats are now recorded in true turn order (Forge picks who goes first). `tools/fix_seats.py` repairs
  batches played before the fix from their play-by-play.
- Windows, macOS and Linux launchers and setup scripts; CI build and smoke test on all three.
