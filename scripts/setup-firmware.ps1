param([switch]$Esp32)
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
& $nodeCommand.Source -e "require(process.argv[1]); console.log('Motor Pico/Pico 2 instalado.');" (Join-Path $workerPath "node_modules/rp2350js")
if ($LASTEXITCODE -ne 0) { throw "Falha ao verificar o motor Pico." }
if ($Esp32) {
    if (-not [Environment]::Is64BitOperatingSystem) { throw "ESP32 requer Windows de 64 bits." }
    $toolsPath = Join-Path $repoRoot "var/tools"
    New-Item -ItemType Directory -Force $toolsPath | Out-Null
    $archivePath = Join-Path $toolsPath "etree-esp32-1.1.0-win64.zip"
    $expected = "3933c9ab3a6ace08ecd34e029efc9b7362c032d86a0a2e76c4ee1693b68fc7d9"
    if (-not (Test-Path -LiteralPath $archivePath)) {
        Invoke-WebRequest "https://github.com/electronicstree/etree-esp32/releases/download/v1.1.0/etree-esp32-1.1.0-win64.zip" -OutFile $archivePath
    }
    if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
        throw "SHA-256 do motor ESP32 não confere. O arquivo não será extraído."
    }
    $engineDirectory = Join-Path $toolsPath "esp32-engine-1.1.0"
    Expand-Archive -LiteralPath $archivePath -DestinationPath $engineDirectory -Force
    Write-Host "Motor ESP32 instalado em $engineDirectory (licenças preservadas). Reinicie o Ohmnia."
}
