$ErrorActionPreference = 'Stop'

$homeDir = [Environment]::GetFolderPath('UserProfile')
$reachDir = Join-Path $homeDir '.agent-reach'
$venvDir = Join-Path $homeDir '.agent-reach-venv'
$configPath = Join-Path $reachDir 'config\mcporter.json'
$sourceDir = Join-Path $reachDir ('src\Agent-Reach-1.4.0-' + (Get-Date -Format 'yyyyMMddHHmmss'))
$zipPath = "$sourceDir.zip"

function Require-Command([string]$name) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $command) { throw "Required command not found: $name" }
    return $command
}

$python = (Require-Command 'python').Source
$node = (Require-Command 'node').Source
$npmCommand = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
if (-not $npmCommand) { $npmCommand = Require-Command 'npm' }

New-Item -ItemType Directory -Force -Path $reachDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $configPath) | Out-Null

if (-not (Test-Path (Join-Path $venvDir 'Scripts\python.exe'))) {
    & $python -m venv $venvDir
}
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$agentReach = Join-Path $venvDir 'Scripts\agent-reach.exe'

try {
    & $venvPython -m pip install --upgrade 'https://github.com/Panniantong/agent-reach/archive/main.zip'
    if ($LASTEXITCODE -ne 0) { throw 'Direct Agent Reach install failed' }
} catch {
    Write-Host 'Direct install failed. Applying the Windows packaging compatibility fix to a local source copy.'
    Invoke-WebRequest -Uri 'https://github.com/Panniantong/agent-reach/archive/refs/tags/v1.4.0.zip' -OutFile $zipPath
    New-Item -ItemType Directory -Force -Path $sourceDir | Out-Null
    Expand-Archive -LiteralPath $zipPath -DestinationPath $sourceDir -Force
    $projectDir = Get-ChildItem -LiteralPath $sourceDir -Directory | Select-Object -First 1
    if (-not $projectDir) { throw 'Agent Reach source directory was not found after extraction.' }
    $pyproject = Join-Path $projectDir.FullName 'pyproject.toml'
    $remove = @(
        '[tool.hatch.build.targets.wheel.force-include]',
        '"agent_reach/guides" = "agent_reach/guides"',
        '"agent_reach/skill" = "agent_reach/skill"',
        '"agent_reach/scripts" = "agent_reach/scripts"'
    )
    $lines = Get-Content -LiteralPath $pyproject
    foreach ($required in $remove) {
        if ($lines -notcontains $required) { throw "Expected packaging line not found: $required" }
    }
    $text = (($lines | Where-Object { $_ -notin $remove }) -join "`n") + "`n"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($pyproject, $text, $utf8NoBom)
    & $venvPython -m pip install --upgrade $projectDir.FullName
    if ($LASTEXITCODE -ne 0) { throw 'Patched Agent Reach install failed' }
}

& $npmCommand.Source install -g mcporter
if ($LASTEXITCODE -ne 0) { throw 'mcporter install failed' }
$mcporterCommand = Get-Command 'mcporter.cmd' -ErrorAction SilentlyContinue
if (-not $mcporterCommand) { $mcporterCommand = Require-Command 'mcporter' }
& $mcporterCommand.Source --config $configPath config add exa https://mcp.exa.ai/mcp
if ($LASTEXITCODE -ne 0) { throw 'Exa MCP configuration failed' }

$ytConfig = Join-Path $homeDir 'AppData\Roaming\yt-dlp\config'
New-Item -ItemType Directory -Force -Path (Split-Path $ytConfig) | Out-Null
if (-not (Test-Path $ytConfig) -or -not (Select-String -LiteralPath $ytConfig -Pattern '--js-runtimes' -Quiet)) {
    Add-Content -LiteralPath $ytConfig -Value '--js-runtimes node'
}

$env:Path = (Join-Path $venvDir 'Scripts') + ';' + (Join-Path $homeDir 'AppData\Roaming\npm') + ';' + $env:Path
$env:PYTHONUTF8 = '1'
Push-Location $reachDir
try {
    & $agentReach doctor
} finally {
    Pop-Location
}

Write-Host "Agent Reach bootstrap complete. Public config: $configPath"
