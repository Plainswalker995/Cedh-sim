# cedh-sim launcher for Windows PowerShell: .\cedh-sim.ps1 run 120
Set-Location -Path $PSScriptRoot
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
& $py -m cedh_sim @args
exit $LASTEXITCODE
