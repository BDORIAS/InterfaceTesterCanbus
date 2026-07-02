param(
    [switch]$SkipInstall,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Remove-SafeDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathToRemove
    )

    $resolvedRoot = [System.IO.Path]::GetFullPath($Root)
    $resolvedTarget = [System.IO.Path]::GetFullPath($PathToRemove)
    if (-not $resolvedTarget.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Ruta fuera del workspace: $resolvedTarget"
    }
    if (Test-Path -LiteralPath $resolvedTarget) {
        Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
    }
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$DistDir = Join-Path $Root "dist\InterfaceTester"
$BuildDir = Join-Path $Root "build"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    python -m venv .venv
}

if (-not $SkipInstall) {
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r requirements.txt
}

if (-not $SkipTests) {
    & $VenvPython -m unittest discover -s tests
}

Remove-SafeDirectory -PathToRemove $DistDir
Remove-SafeDirectory -PathToRemove $BuildDir

& $VenvPython setup.py build_exe --build-exe $DistDir

Write-Host ""
Write-Host "Build listo en: $DistDir"
Write-Host "Ejecutable: $(Join-Path $DistDir 'InterfaceTester.exe')"
Write-Host ""
Write-Host "Distribucion recomendada:"
Write-Host "- Entregar la carpeta completa dist\InterfaceTester."
Write-Host "- No comprimir con UPX."
Write-Host "- Firmar InterfaceTester.exe con signtool para reducir alertas de SmartScreen."
Write-Host "- Para generar ZIP/checksum: .\package_release.ps1 -SkipBuild"
