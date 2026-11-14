#!/usr/bin/env bash
# Builds the patched Forge engine into ./forge (macOS and Linux).
# Needs: git, a JDK 17 or newer, Maven 3.8+ and Python 3.10+.
set -euo pipefail
cd "$(dirname "$0")/.."
here="$(pwd)"
commit="$(tr -d '[:space:]' < forge-patch/FORGE_COMMIT)"
for tool in git java mvn python3; do
  command -v "$tool" >/dev/null || { echo "Missing $tool. See README, Setup." >&2; exit 1; }
done
if [ ! -d forge/.git ]; then
  git init -q forge
  git -C forge remote add origin https://github.com/Card-Forge/forge.git
fi
echo "Fetching Forge at $commit ..."
git -C forge fetch -q --depth 1 origin "$commit"
git -C forge reset -q --hard FETCH_HEAD
git -C forge clean -fdq
echo "Applying the cEDH patch ..."
git -C forge apply --whitespace=nowarn "$here/forge-patch/cedh.patch"
echo "Building (the first build downloads dependencies and takes a few minutes) ..."
(cd forge && mvn -q -B -DskipTests -Dcheckstyle.skip -pl forge-gui-desktop -am install)
python3 -m cedh_sim check
