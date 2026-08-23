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

function Test-DockerRuntime {
    $dockerConfig = New-DockerConfigDir
    $probe = Run-Command -FilePath 'docker' -Arguments @('--config', $dockerConfig, 'version')
    if ($probe.ExitCode -ne 0) {
        $reason = if ($probe.Stderr) { $probe.Stderr } else { $probe.Stdout }
        return [pscustomobject]@{ Ready = $false; Reason = $reason }
    }
    return [pscustomobject]@{ Ready = $true; Reason = 'docker daemon reachable' }
}

function Test-PinnedRuntime {
    param([string]$Image)
    $dockerConfig = New-DockerConfigDir
    $inspect = Run-Command -FilePath 'docker' -Arguments @('--config', $dockerConfig, 'image', 'inspect', $Image)
    if ($inspect.ExitCode -ne 0) {
        $reason = if ($inspect.Stderr) { $inspect.Stderr } else { $inspect.Stdout }
        return [pscustomobject]@{ Ready = $false; Reason = $reason }
    }
    $version = Run-Command -FilePath 'docker' -Arguments @('--config', $dockerConfig, 'run', '--rm', $Image, 'codex', '--version')
    if ($version.ExitCode -ne 0) {
        $reason = if ($version.Stderr) { $version.Stderr } else { $version.Stdout }
        return [pscustomobject]@{ Ready = $false; Reason = $reason }
    }
    $reason = if ($version.Stdout) { $version.Stdout } else { 'codex runtime reachable' }
    return [pscustomobject]@{ Ready = $true; Reason = $reason }
}

function Test-CodexLoginStatus {
    param([string]$Image, [string]$CodexHomePath)
    New-Item -ItemType Directory -Force -Path $CodexHomePath | Out-Null
    $dockerConfig = New-DockerConfigDir
    $mount = "$($CodexHomePath):/codex-home"
    $envMap = @{
        HOME = '/codex-home'
        CODEX_HOME = '/codex-home'
    }
    $probe = Run-Command -FilePath 'docker' -Arguments @('--config', $dockerConfig, 'run', '--rm', '-e', 'HOME=/codex-home', '-e', 'CODEX_HOME=/codex-home', '-v', $mount, $Image, 'codex', 'login', 'status') -Environment $envMap
    if ($probe.ExitCode -eq 0) {
        $detail = if ($probe.Stdout) { $probe.Stdout } else { 'codex login status ok' }
        return [pscustomobject]@{ Ready = $true; Status = 'AUTHENTICATED'; Detail = $detail }
    }
    $detail = if ($probe.Stderr) { $probe.Stderr } elseif ($probe.Stdout) { $probe.Stdout } else { 'codex login status failed' }
    return [pscustomobject]@{ Ready = $false; Status = 'UNAUTHENTICATED'; Detail = $detail }
}

$docker = Test-DockerRuntime
$runtime = if ($docker.Ready) { Test-PinnedRuntime -Image $PinnedImage } else { [pscustomobject]@{ Ready = $false; Reason = 'docker runtime unavailable' } }

Emit 'DOCKER_RUNTIME_READY' $docker.Ready
Emit 'PINNED_CODEX_RUNTIME_READY' $runtime.Ready
Emit 'EPHEMERAL_CODEX_HOME' $CodexHome

if (-not $docker.Ready -or -not $runtime.Ready) {
    Emit 'EPHEMERAL_CODEX_LOGIN_STATUS' 'UNAVAILABLE'
    Emit 'CODEX_AUTH_READY' $false
    Emit 'ATTEMPT_CREATED' $false
    Emit 'REAL_CODEX_EXEC' 0
    Emit 'NEXT_SINGLE_ACTION' 'Fix Docker/runtime access, then rerun this script with the same ephemeral CODEX_HOME'
    exit 0
}

$login = Test-CodexLoginStatus -Image $PinnedImage -CodexHomePath $CodexHome
Emit 'EPHEMERAL_CODEX_LOGIN_STATUS' ("{0}: {1}" -f $login.Status, $login.Detail)
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
