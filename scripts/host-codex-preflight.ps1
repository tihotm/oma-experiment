param(
    [string]$CodexHome = $(if ($env:OMA7_EPHEMERAL_CODEX_HOME) { $env:OMA7_EPHEMERAL_CODEX_HOME } else { Join-Path $env:TEMP 'oma7-ephemeral-codex-home' }),
    [string]$PinnedImage = $(if ($env:OMA7_PINNED_CODEX_IMAGE) { $env:OMA7_PINNED_CODEX_IMAGE } else {
        $python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
        $repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
        $probe = & $python -c "import sys; sys.path.insert(0, r'$repoRoot\\src'); from oma7.preflight import DEFAULT_CODEX_IMAGE_REF; print(DEFAULT_CODEX_IMAGE_REF)"
        $probe.Trim()
    })
)

$ErrorActionPreference = 'Stop'

function Emit([string]$Key, [object]$Value) {
    Write-Output ("{0}={1}" -f $Key, $Value)
}

function Resolve-CliPath([string[]]$EnvNames, [string[]]$StandardPaths, [string]$UnavailableReason) {
    foreach ($name in $EnvNames) {
        $value = (Get-Item ("Env:{0}" -f $name) -ErrorAction SilentlyContinue).Value
        if ($value) {
            return [pscustomobject]@{ Ready = $true; Path = $value; Source = "env:$name"; Reason = 'explicit CLI path provided' }
        }
    }
    foreach ($candidate in $StandardPaths) {
        if (Test-Path -LiteralPath $candidate) {
            return [pscustomobject]@{ Ready = $true; Path = $candidate; Source = "installed:$candidate"; Reason = 'standard install location' }
        }
    }
    return [pscustomobject]@{ Ready = $false; Path = $null; Source = $null; Reason = $UnavailableReason }
}

function Test-CodexCli {
    Resolve-CliPath -EnvNames @('OMA7_CODEX_CLI_PATH', 'CODEX_CLI_PATH') -StandardPaths @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Codex\codex.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\OpenAI Codex\codex.exe')
    ) -UnavailableReason 'codex executable unavailable'
}

function Run-Command([string]$FilePath, [string[]]$Arguments, [hashtable]$Environment = $null) {
    if ($Environment) {
        foreach ($entry in $Environment.GetEnumerator()) {
            Set-Item -Path ("Env:{0}" -f $entry.Key) -Value ([string]$entry.Value)
        }
    }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $Arguments -join ' '
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $process = [System.Diagnostics.Process]::Start($psi)
    if (-not $process) {
        throw "Failed to start process $FilePath"
    }
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    $exitCode = $process.ExitCode

    [pscustomobject]@{
        ExitCode = $exitCode
        Stdout   = $stdout.Trim()
        Stderr   = $stderr.Trim()
    }
}

function New-DockerConfigDir {
    $dir = Join-Path $env:TEMP '.oma7-docker-config'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Test-DockerCli {
    Resolve-CliPath -EnvNames @('OMA7_DOCKER_CLI_PATH', 'DOCKER_CLI_PATH') -StandardPaths @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Docker Desktop\resources\bin\docker.exe'),
        'C:\Program Files\Docker\Docker\resources\bin\docker.exe',
        'C:\Program Files\Docker Desktop\resources\bin\docker.exe'
    ) -UnavailableReason 'docker executable unavailable'
}

function Test-DockerRuntime {
    param([string]$DockerPath)
    $dockerConfig = New-DockerConfigDir
    $probe = Run-Command -FilePath $DockerPath -Arguments @('--config', $dockerConfig, 'version')
    if ($probe.ExitCode -ne 0) {
        $reason = if ($probe.Stderr) { $probe.Stderr } else { $probe.Stdout }
        return [pscustomobject]@{ Ready = $false; Reason = $reason }
    }
    return [pscustomobject]@{ Ready = $true; Reason = 'docker daemon reachable' }
}

function Test-PinnedRuntime {
    param([string]$DockerPath, [string]$Image)
    $dockerConfig = New-DockerConfigDir
    $inspect = Run-Command -FilePath $DockerPath -Arguments @('--config', $dockerConfig, 'image', 'inspect', $Image)
    if ($inspect.ExitCode -ne 0) {
        $reason = if ($inspect.Stderr) { $inspect.Stderr } else { $inspect.Stdout }
        return [pscustomobject]@{ Ready = $false; Reason = $reason }
    }
    $version = Run-Command -FilePath $DockerPath -Arguments @('--config', $dockerConfig, 'run', '--rm', $Image, 'codex', '--version')
    if ($version.ExitCode -ne 0) {
        $reason = if ($version.Stderr) { $version.Stderr } else { $version.Stdout }
        return [pscustomobject]@{ Ready = $false; Reason = $reason }
    }
    $reason = if ($version.Stdout) { $version.Stdout } else { 'codex runtime reachable' }
    return [pscustomobject]@{ Ready = $true; Reason = $reason }
}

function Test-CodexLoginStatus {
    param([string]$DockerPath, [string]$Image, [string]$CodexHomePath)
    New-Item -ItemType Directory -Force -Path $CodexHomePath | Out-Null
    $dockerConfig = New-DockerConfigDir
    $mount = "$($CodexHomePath):/codex-home"
    $envMap = @{
        HOME = '/codex-home'
        CODEX_HOME = '/codex-home'
    }
    $probe = Run-Command -FilePath $DockerPath -Arguments @('--config', $dockerConfig, 'run', '--rm', '-e', 'HOME=/codex-home', '-e', 'CODEX_HOME=/codex-home', '-v', $mount, $Image, 'codex', 'login', 'status') -Environment $envMap
    if ($probe.ExitCode -eq 0) {
        $detail = if ($probe.Stdout) { $probe.Stdout } else { 'codex login status ok' }
        return [pscustomobject]@{ Ready = $true; Status = 'AUTHENTICATED'; Detail = $detail }
    }
    $detail = if ($probe.Stderr) { $probe.Stderr } elseif ($probe.Stdout) { $probe.Stdout } else { 'codex login status failed' }
    return [pscustomobject]@{ Ready = $false; Status = 'UNAUTHENTICATED'; Detail = $detail }
}

function Test-CodexLoginStatusLocal {
    param([string]$CodexPath, [string]$CodexHomePath)
    New-Item -ItemType Directory -Force -Path $CodexHomePath | Out-Null
    $probe = Run-Command -FilePath $CodexPath -Arguments @('login', 'status') -Environment @{
        CODEX_HOME = $CodexHomePath
    }
    if ($probe.ExitCode -eq 0) {
        $detail = if ($probe.Stdout) { $probe.Stdout } else { 'codex login status ok' }
        return [pscustomobject]@{ Ready = $true; Status = 'AUTH_READY'; Detail = $detail }
    }
    $detail = if ($probe.Stderr) { $probe.Stderr } elseif ($probe.Stdout) { $probe.Stdout } else { 'codex login status failed' }
    return [pscustomobject]@{ Ready = $false; Status = 'AUTH_NOT_READY'; Detail = $detail }
}

$dockerCli = Test-DockerCli
$docker = if ($dockerCli.Ready) { Test-DockerRuntime -DockerPath $dockerCli.Path } else { [pscustomobject]@{ Ready = $false; Reason = 'docker executable unavailable' } }
$runtime = if ($docker.Ready) { Test-PinnedRuntime -DockerPath $dockerCli.Path -Image $PinnedImage } else { [pscustomobject]@{ Ready = $false; Reason = 'docker runtime unavailable' } }
$codexCli = Test-CodexCli

Emit 'DOCKER_RUNTIME_READY' $docker.Ready
Emit 'PINNED_CODEX_RUNTIME_READY' $runtime.Ready
Emit 'EPHEMERAL_CODEX_HOME' $CodexHome
Emit 'CODEX_CLI_CAPABILITY' ($(if ($codexCli.Ready) { 'CLI_AVAILABLE' } else { 'CLI_ABSENT' }))
Emit 'CODEX_CLI_REASON' $codexCli.Reason
Emit 'HOST_CAPABILITY_SUPPORT' ($(if ($dockerCli.Ready -and $codexCli.Ready) { 'SUPPORTED' } else { 'BLOCKED' }))
Emit 'HOST_DOCKER_CLI_PATH' ($dockerCli.Path)
Emit 'HOST_DOCKER_CLI_SOURCE' ($dockerCli.Source)
Emit 'HOST_CODEX_CLI_PATH' ($codexCli.Path)
Emit 'HOST_CODEX_CLI_SOURCE' ($codexCli.Source)
Emit 'HOST_CAPABILITY_BLOCKERS' ($(if ($dockerCli.Ready -and $codexCli.Ready) { '()' } else { @($dockerCli.Reason, $codexCli.Reason) -join ',' }))

if (-not $docker.Ready -or -not $runtime.Ready) {
    Emit 'EPHEMERAL_CODEX_LOGIN_STATUS' 'UNAVAILABLE'
    Emit 'CODEX_AUTH_STATUS' 'NOT_PROBED'
    Emit 'CODEX_AUTH_READY' $false
    Emit 'ATTEMPT_CREATED' $false
    Emit 'REAL_CODEX_EXEC' 0
    Emit 'NEXT_SINGLE_ACTION' 'Fix Docker/runtime access, then rerun this script with the same ephemeral CODEX_HOME'
    exit 0
}

if (-not $codexCli.Ready) {
    Emit 'EPHEMERAL_CODEX_LOGIN_STATUS' 'UNAVAILABLE'
    Emit 'CODEX_AUTH_STATUS' 'NOT_PROBED'
    Emit 'CODEX_AUTH_READY' $false
    Emit 'ATTEMPT_CREATED' $false
    Emit 'REAL_CODEX_EXEC' 0
    Emit 'NEXT_SINGLE_ACTION' 'Make the Codex CLI available in the host/runtime path, then rerun this script'
    exit 0
}

$login = Test-CodexLoginStatusLocal -CodexPath $codexCli.Path -CodexHomePath $CodexHome
Emit 'EPHEMERAL_CODEX_LOGIN_STATUS' ("{0}: {1}" -f $login.Status, $login.Detail)
Emit 'CODEX_AUTH_STATUS' $login.Status
Emit 'CODEX_AUTH_READY' $login.Ready

if (-not $login.Ready) {
    Emit 'ATTEMPT_CREATED' $false
    Emit 'REAL_CODEX_EXEC' 0
    Emit 'NEXT_SINGLE_ACTION' ("Run: codex login (same CODEX_HOME={0})" -f $CodexHome)
    exit 0
}

Emit 'ATTEMPT_CREATED' $true
Emit 'REAL_CODEX_EXEC' 1

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pipeline = Join-Path $repoRoot 'host_docker_e2e.py'
$python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }

$pipelineResult = Run-Command -FilePath $python -Arguments @($pipeline)
if ($pipelineResult.ExitCode -ne 0) {
    Emit 'MINIMAL_MISSION_RESULT' 'BLOCKED'
    Emit 'NEXT_SINGLE_ACTION' 'Inspect host_docker_e2e.py output and fix the failing production step'
    exit 1
}

Emit 'MINIMAL_MISSION_RESULT' 'COMPLETED'
Emit 'NEXT_SINGLE_ACTION' 'Inspect emitted execution evidence and persist CURRENT-WORK.md only from executed evidence'
exit 0
