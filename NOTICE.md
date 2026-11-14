# Notices

## Forge

This project runs games on [Forge](https://github.com/Card-Forge/forge), an open-source Magic: The Gathering
rules engine, copyright the Forge developers, licensed under the GNU General Public License v3.0.
Forge itself is not included here. `scripts/setup.sh` / `scripts/setup.ps1` download Forge's source at the
commit named in `forge-patch/FORGE_COMMIT` and apply `forge-patch/cedh.patch`.

`forge-patch/cedh.patch` is this project's change to Forge, also under GPL-3.0. It touches these files
(list kept current in `forge-patch/FILES.txt`):

- New: `forge-ai/.../simulation/CedhPilot.java` (cEDH habits: fast mana and commanders early, the
  Underworld Breach loop, tutoring for the Thassa's Oracle line, the learned mulligan model, human-like slips),
  `forge-gui-desktop/.../view/CedhSim.java` (the headless batch runner), and the AI profiles
  `forge-gui/res/ai/Cedh.ai`, `CedhAggro.ai`, `CedhPatient.ai`.
- Changed: `AiController.java`, `PlayerControllerAi.java`, `ability/MillAi.java`, `ability/ChangeZoneAi.java`,
  `simulation/ConsultationWin.java` (hooks into the pilot), `view/Main.java` (the `cedh` mode).

## Magic: The Gathering

cEDH sim is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy. It is not
approved or endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast.
©Wizards of the Coast LLC. It is free and non-commercial and contains no card images.
