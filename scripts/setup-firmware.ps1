$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $nodeCommand -or -not $npmCommand) {
    throw "Instale o Node.js LTS (incluindo npm) e abra um novo terminal."
}
$workerPath = Join-Path $repoRoot "backend/src/circuitos/cosim/firmware_worker"
& $npmCommand.Source ci --ignore-scripts --prefix $workerPath
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar o motor AVR8js." }
& $nodeCommand.Source -e "require(process.argv[1]); console.log('Motor AVR instalado.');" (Join-Path $workerPath "node_modules/avr8js")
if ($LASTEXITCODE -ne 0) { throw "Falha ao verificar o motor AVR8js." }
