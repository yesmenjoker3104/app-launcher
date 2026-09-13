$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$Python = join-path $Root ".venv\Scripts\python.exe"

if (-Not (Test-Path $Python)) {
    $BootstrapPython = Get-Command python -ErrorAction SilentlyContinue
    if (-not $BootstrapPython) {
        $BootstrapPython = Get-Command py -ErrorAction SilentlyContinue
    }
    if (-not $BootstrapPython) {
        throw "Python was not found."
    }
    & $BootstrapPython.Source -m venv (Join-Path $Root ".venv")
}

& $Python -m pip install --upgrade pip
& $Python -m pip install  pyinstaller

push-location $Root

try{
    & $Python -m PyInstaller `
    --onefile `
    --console `
    --clean `
    --noconfirm `
    --name AppLauncherCli `
    --paths "$Root\src" `
    --distpath "$Root\dist" `
    --workpath "$Root\build\AppLauncherCli" `
    "$Root\cli_entry.py"
}
finally{
    pop-location
}

$Exe = join-path $Root "dist\AppLauncherCli.exe"
if (-not (test-path $Exe)) {
    throw "Build failed: $Exe not found."
}

$DataTargetDir = join-path $Root "dist\data"
$DataFiles = @("apps.json", "config.json")
foreach ($DataFile in $DataFiles) {
    $DataSource = join-path $Root "data\$DataFile"
    if (test-path $DataSource) {
        new-item -ItemType Directory -Force $DataTargetDir | out-null
        copy-item $DataSource (join-path $DataTargetDir $DataFile) -Force
        write-host "Copied data: $DataTargetDir\$DataFile"
    }
}

write-host "Build succeeded: $Exe"
