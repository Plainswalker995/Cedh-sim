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
- Open mana is used: in the second main phase a pilot casts the biggest threat, engine or other permanent it
  can afford instead of ending the turn holding it (combo pieces stay held for their line).
- Tutors no longer sit in hand: Vampiric Tutor, Imperial Seal, Mystical and Worldly Tutor fetch the missing half
  of the Thassa's Oracle line, and with neither half in hand a tutor starts the line with the Oracle.
- Cheap draw engines (Mystic Remora, Rhystic Study, Esper Sentinel, Necropotence and the like) are deployed early,
  after fast mana and before the commanders, instead of sitting in hand.
- Mulligans: after the free first mulligan, a seven is judged against the six it would become, so decent sevens
  are kept.
- Fix: the loss-reason report crashed on newer game records.
- Fix: seats are now recorded in true turn order (Forge picks who goes first). `tools/fix_seats.py` repairs
  batches played before the fix from their play-by-play.
- Windows, macOS and Linux launchers and setup scripts; CI build and smoke test on all three.
- With nothing to deploy, a pilot casts a tutor or draw spell in its second main phase instead of holding it
  (a wheel only when the rest of its hand is small and holds no combo piece). Diabolic Intent can fetch a
  Thassa's Oracle half.
- Draw causes no longer count reactive cards (Commandeer, Flare of Duplication) or sacrifice rituals held in
  hand as mistakes.
- Learned in-game decisions (design choice): every pilot logs three choices with what it could see at the time
  (opponents' open mana and hand sizes, its own protection, mana and the round): cast the winning line now or wait
  a turn, tutor for protection before going off, and counter an opponent's spell or keep the counterspell. Spells
  that win are always countered. `train` fits a small logistic model per choice (numpy, no GPU) once there are
  enough examples of both options, and the promotion gate decides whether it replaces the hand-written rule.
- Exploration (design choice): to learn, a pilot sometimes takes the other option on purpose (`--explore`; 5% in
  `auto`, 0 in `run` and `swap`, 20% in the new `gather` command). Set-up positions count as data for the
  go-or-wait and protect-first choices, since a win is on the table every game there.
- `metrics --run-known --known NAME` reruns one known-answer test; a flaky read of a shared folder no longer
  stops a batch.
- Fix: when a worker stops early (out of memory in one very long game), the games it had left are played again
  in a fresh worker with more memory instead of silently missing from the batch.
