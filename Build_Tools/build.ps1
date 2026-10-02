$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Project .venv is missing' }
$runtimePaths = & $pythonPath -c "import sys, pathlib, PySide6; p=pathlib.Path(PySide6.__file__).parent; print(str(p)); print(str(p.parent/'shiboken6')); print(sys.base_prefix); print(str(pathlib.Path(sys.base_prefix)/'DLLs'))"
if ($LASTEXITCODE -ne 0) { throw 'Cannot locate selected runtime' }
$env:PATH = (@((Split-Path -Parent $pythonPath)) + @($runtimePaths) + @((Join-Path $env:SystemRoot 'System32'))) -join ';'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath $projectRoot
$oldBuild = Join-Path $projectRoot 'KeyShelf'
if (Test-Path -LiteralPath $oldBuild) {
    $resolvedBuild = (Resolve-Path -LiteralPath $oldBuild).Path
    if ($resolvedBuild -ne (Join-Path $projectRoot 'KeyShelf') -or
        (Get-Item -LiteralPath $resolvedBuild).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unsafe build target' }
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedBuild 'RUNTIME_MANIFEST.json'))) { throw 'Unrecognized previous build folder' }
    Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
}
& $pythonPath -m PyInstaller (Join-Path $PSScriptRoot 'KeyShelf.spec') --clean --noconfirm --distpath (Join-Path $PSScriptRoot 'dist') --workpath (Join-Path $PSScriptRoot 'build')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
& $pythonPath (Join-Path $PSScriptRoot 'post_build.py')
if ($LASTEXITCODE -ne 0) { throw 'Post-build failed' }
