# Builds the patched Forge engine into .\forge (Windows).
# Needs: git, a JDK 17 or newer, Maven 3.8+ and Python 3.10+ on PATH.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$here = (Get-Location).Path
$commit = (Get-Content "forge-patch\FORGE_COMMIT" -Raw).Trim()
foreach ($tool in "git", "java", "mvn") {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Missing $tool. See README, Setup." }
}
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
function Run($exe, [string[]]$argList) { & $exe @argList; if ($LASTEXITCODE -ne 0) { throw "$exe failed" } }
if (-not (Test-Path "forge\.git")) {
  Run git @("init", "-q", "forge")
  Run git @("-C", "forge", "remote", "add", "origin", "https://github.com/Card-Forge/forge.git")
}
Write-Host "Fetching Forge at $commit ..."
Run git @("-C", "forge", "fetch", "-q", "--depth", "1", "origin", $commit)
Run git @("-C", "forge", "reset", "-q", "--hard", "FETCH_HEAD")
Run git @("-C", "forge", "clean", "-fdq")
Write-Host "Applying the cEDH patch ..."
Run git @("-C", "forge", "apply", "--whitespace=nowarn", (Join-Path $here "forge-patch\cedh.patch"))
Write-Host "Building (the first build downloads dependencies and takes a few minutes) ..."
Push-Location forge
Run mvn @("-q", "-B", "-DskipTests", "-Dcheckstyle.skip", "-pl", "forge-gui-desktop", "-am", "install")
Pop-Location
Run $py @("-m", "cedh_sim", "check")
