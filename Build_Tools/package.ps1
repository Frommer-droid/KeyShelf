param(
    [string]$InnoCompilerPath = $env:INNO_SETUP_ISCC,
    [string]$PortableDirectory = $env:KEYSHELF_PORTABLE_DIR,
    [switch]$SkipPortableCopy
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $pythonPath (Join-Path $PSScriptRoot 'payload_policy.py') (Join-Path $projectRoot 'KeyShelf')
if ($LASTEXITCODE -ne 0) { throw 'Unsafe release payload' }
if (-not $InnoCompilerPath) {
    $compilerCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($compilerCommand) { $InnoCompilerPath = $compilerCommand.Source }
}
if (-not $InnoCompilerPath) {
    $compilerCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )
    foreach ($registryPath in @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1'
    )) {
        $installed = Get-ItemProperty -LiteralPath $registryPath -ErrorAction SilentlyContinue
        if ($installed.InstallLocation) {
            $compilerCandidates += Join-Path $installed.InstallLocation 'ISCC.exe'
        }
    }
    $InnoCompilerPath = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $InnoCompilerPath -or -not (Test-Path -LiteralPath $InnoCompilerPath -PathType Leaf)) {
    throw 'Inno Setup compiler unavailable. Set INNO_SETUP_ISCC or pass -InnoCompilerPath.'
}
$iscc = (Resolve-Path -LiteralPath $InnoCompilerPath).Path
$shell = New-Object -ComObject WScript.Shell
$desktop = $shell.SpecialFolders.Item('Desktop')
if (-not [IO.Path]::IsPathRooted($desktop)) { throw 'Windows Desktop cannot be resolved' }
& $iscc "/O$desktop" (Join-Path $PSScriptRoot 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
$version = (Get-Content -LiteralPath (Join-Path $projectRoot 'VERSION') -Raw).Trim()
Write-Output "Installer: $(Join-Path $desktop "KeyShelf_v${version}_Setup.exe")"
if ($SkipPortableCopy) { return }
if (-not $PortableDirectory) { $PortableDirectory = 'D:\Portable_soft\KeyShelf' }
if (-not [IO.Path]::IsPathRooted($PortableDirectory)) { throw 'Portable directory must be absolute' }
$destination = [IO.Path]::GetFullPath($PortableDirectory).TrimEnd('\')
if ($destination -eq [IO.Path]::GetPathRoot($destination).TrimEnd('\') -or
    $destination -eq $projectRoot -or $destination.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Unsafe portable directory'
}
$deployRoot = Split-Path -Parent $destination
if (Test-Path -LiteralPath $destination) {
    $resolvedDestination = (Resolve-Path -LiteralPath $destination).Path
    if ($resolvedDestination -ne $destination -or
        (Get-Item -LiteralPath $resolvedDestination).Attributes -band [IO.FileAttributes]::ReparsePoint -or
        -not (Test-Path -LiteralPath (Join-Path $resolvedDestination 'RUNTIME_MANIFEST.json'))) { throw 'Unrecognized portable folder' }
}
New-Item -ItemType Directory -Path $deployRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $destination)) { New-Item -ItemType Directory -Path $destination | Out-Null }
foreach ($payload in (Get-ChildItem -LiteralPath (Join-Path $projectRoot 'KeyShelf') -Force)) {
    Copy-Item -LiteralPath $payload.FullName -Destination $destination -Recurse -Force
}
Write-Output "Portable: $destination"
