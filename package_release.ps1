param(
    [switch]$SkipBuild,
    [switch]$SkipInstall,
    [switch]$SkipTests,
    [string]$OutputDir = "Releases"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Get-AppVersion {
    $initPath = Join-Path $Root "interface_tester\__init__.py"
    $content = Get-Content -LiteralPath $initPath -Raw
    $match = [regex]::Match($content, '__version__\s*=\s*"([^"]+)"')
    if (-not $match.Success) {
        throw "No se pudo leer __version__ desde $initPath"
    }
    return $match.Groups[1].Value
}

function Resolve-WorkspacePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathToResolve
    )

    if ([System.IO.Path]::IsPathRooted($PathToResolve)) {
        return [System.IO.Path]::GetFullPath($PathToResolve)
    }

    return [System.IO.Path]::GetFullPath((Join-Path $Root $PathToResolve))
}

function Assert-PathInsideWorkspace {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathToCheck
    )

    $resolvedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $resolvedTarget = [System.IO.Path]::GetFullPath($PathToCheck)
    if (-not $resolvedTarget.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Ruta fuera del workspace: $resolvedTarget"
    }
}

function Remove-SafeDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathToRemove
    )

    Assert-PathInsideWorkspace -PathToCheck $PathToRemove
    if (Test-Path -LiteralPath $PathToRemove) {
        Remove-Item -LiteralPath $PathToRemove -Recurse -Force
    }
}

function Get-RelativePathForChecksum {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseDir,
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )

    $base = [System.IO.Path]::GetFullPath($BaseDir).TrimEnd('\', '/')
    $file = [System.IO.Path]::GetFullPath($FilePath)
    if ($file.StartsWith($base, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $file.Substring($base.Length).TrimStart('\', '/')
    }

    return $file
}

function New-Sha256Line {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string]$BaseDir
    )

    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $FilePath
    $relative = Get-RelativePathForChecksum -BaseDir $BaseDir -FilePath $FilePath
    return "$($hash.Hash.ToLowerInvariant())  $relative"
}

if (-not $SkipBuild) {
    $buildScript = Join-Path $Root "build_windows.ps1"
    $buildArgs = @{}
    if ($SkipInstall) {
        $buildArgs["SkipInstall"] = $true
    }
    if ($SkipTests) {
        $buildArgs["SkipTests"] = $true
    }

    & $buildScript @buildArgs
}

$version = Get-AppVersion
$distDir = Join-Path $Root "dist\InterfaceTester"
$exePath = Join-Path $distDir "InterfaceTester.exe"

if (-not (Test-Path -LiteralPath $exePath)) {
    throw "No existe el ejecutable esperado: $exePath. Ejecuta .\build_windows.ps1 primero o quita -SkipBuild."
}

$releaseRoot = Resolve-WorkspacePath -PathToResolve $OutputDir
Assert-PathInsideWorkspace -PathToCheck $releaseRoot

$packageName = "InterfaceTester-v$version-win"
$stageDir = Join-Path $releaseRoot $packageName
$zipPath = Join-Path $releaseRoot "$packageName.zip"
$checksumPath = Join-Path $releaseRoot "$packageName.sha256.txt"

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
Remove-SafeDirectory -PathToRemove $stageDir
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

Get-ChildItem -LiteralPath $distDir -Force | Copy-Item -Destination $stageDir -Recurse -Force

$createdAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss K"
$manifest = [ordered]@{
    application = "InterfaceTester"
    version = $version
    created_at = $createdAt
    executable = "InterfaceTester.exe"
    source_dist = "dist\InterfaceTester"
    packaging = "Folder distribution plus ZIP archive"
    sim_host_policy = "Sim Host is assumed to be already downloaded; this app does not control it."
}

($manifest | ConvertTo-Json -Depth 3) | Set-Content -LiteralPath (Join-Path $stageDir "release_manifest.json") -Encoding UTF8

$notes = @(
    "InterfaceTester v$version",
    "",
    "Contenido:",
    "- InterfaceTester.exe y dependencias generadas por cx_Freeze.",
    "- Los archivos .dat no estan incluidos; deben cargarse externamente desde la GUI.",
    "- release_manifest.json con metadata del paquete.",
    "- SHA256SUMS.txt con hashes de los archivos incluidos.",
    "",
    "Notas de uso:",
    "- Distribuir la carpeta completa, no solo InterfaceTester.exe.",
    "- No usar UPX ni compresores de ejecutable.",
    "- Para reducir alertas de Windows Defender/SmartScreen, firmar InterfaceTester.exe con certificado de firma de codigo.",
    "- La app trabaja en Direct Mode y asume que Sim Host ya esta descargado."
)
$notes | Set-Content -LiteralPath (Join-Path $stageDir "RELEASE_NOTES.txt") -Encoding UTF8

$stageChecksumPath = Join-Path $stageDir "SHA256SUMS.txt"
$stageFiles = Get-ChildItem -LiteralPath $stageDir -Recurse -File | Where-Object { $_.FullName -ne $stageChecksumPath } | Sort-Object FullName
$stageChecksums = foreach ($file in $stageFiles) {
    New-Sha256Line -FilePath $file.FullName -BaseDir $stageDir
}
$stageChecksums | Set-Content -LiteralPath $stageChecksumPath -Encoding UTF8

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -LiteralPath $stageDir -DestinationPath $zipPath -CompressionLevel Optimal

$zipHash = Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath
@(
    "$($zipHash.Hash.ToLowerInvariant())  $(Split-Path -Leaf $zipPath)"
) | Set-Content -LiteralPath $checksumPath -Encoding UTF8

Write-Host ""
Write-Host "Paquete listo:"
Write-Host "- Carpeta: $stageDir"
Write-Host "- ZIP:     $zipPath"
Write-Host "- SHA256:  $checksumPath"
