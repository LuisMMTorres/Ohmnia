# Builds the Windows package: packaging\dist\Ohmnia\Ohmnia.exe and a .zip to distribute.
#
# Requirements on the build machine: uv, Node.js, and ngspice for Windows (the console package
# "Spice64" and the DLL package "Spice64_dll"), located by CIRCUITOS_NGSPICE_EXE and
# CIRCUITOS_NGSPICE_LIB as in the README.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$work = Join-Path $PSScriptRoot "build"
$stage = Join-Path $work "ngspice"

Write-Host "== interface"
Push-Location (Join-Path $root "frontend")
npm ci --no-audit --no-fund
npm run build
Pop-Location

Write-Host "== ngspice"
if (-not $env:CIRCUITOS_NGSPICE_EXE -or -not $env:CIRCUITOS_NGSPICE_LIB) {
    throw "Defina CIRCUITOS_NGSPICE_EXE e CIRCUITOS_NGSPICE_LIB (veja o README)."
}
$exeDir = Split-Path $env:CIRCUITOS_NGSPICE_EXE          # ...\Spice64\bin
$dllDir = Split-Path $env:CIRCUITOS_NGSPICE_LIB          # ...\Spice64_dll\dll-vs
$dllRoot = Split-Path $dllDir                            # ...\Spice64_dll
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force (Join-Path $stage "bin"), (Join-Path $stage "dll") | Out-Null
Copy-Item (Join-Path $exeDir "*") (Join-Path $stage "bin") -Recurse
Copy-Item (Join-Path $dllDir "*") (Join-Path $stage "dll") -Recurse
# the DLL package lacks the audio libraries the DLL links against (ngspice 47)
foreach ($f in "sndfile.dll", "samplerate.dll") {
    if (-not (Test-Path (Join-Path $stage "dll\$f"))) { Copy-Item (Join-Path $exeDir $f) (Join-Path $stage "dll") }
}
# code models and the init script, where ngspice.dll looks for them (..\lib, ..\share)
foreach ($d in "lib", "share") {
    $src = Join-Path $dllRoot $d
    if (Test-Path $src) { Copy-Item $src $stage -Recurse }
}

Write-Host "== executável"
$env:CIRCUITOS_BUNDLE_NGSPICE = $stage
Push-Location (Join-Path $root "backend")
uv sync --group build
uv run pyinstaller --noconfirm --clean `
    --distpath (Join-Path $PSScriptRoot "dist") --workpath $work `
    (Join-Path $PSScriptRoot "circuitos.spec")
$version = (uv run python -c "import circuitos; print(circuitos.__version__)").Trim()
Pop-Location

Write-Host "== pacote"
$dist = Join-Path $PSScriptRoot "dist\Ohmnia"
Copy-Item (Join-Path $PSScriptRoot "LEIA-ME.txt") $dist
$manual = Join-Path $root "docs\manual"
if (Test-Path $manual) { Copy-Item $manual (Join-Path $dist "manual") -Recurse -Force }
$zip = Join-Path $PSScriptRoot "dist\Ohmnia-$version-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $dist -DestinationPath $zip
Write-Host "Pronto: $zip"
