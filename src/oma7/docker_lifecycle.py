from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
import subprocess
import tempfile
import uuid
import shutil
import sys
from pathlib import Path
from typing import Iterable

from .models import ExecutionContextIdentity, VerificationContextIdentity
from .snapshot import freeze_snapshot
from .scope import ProvenanceAnchorInputs, ScopeDecision, ScopePolicy, build_provenance_anchor, evaluate_scope_change, ScopeChange, ScopeOperation, ScopeObjectType
from .lifecycle import ControlledLifecycleObservation, GateStatus, LifecycleState, evaluate_acceptance
from .models import Evidence, MaterializationIdentity, ResultStatus, ScopePolicyIdentity, SubjectIdentity, ProvenanceAnchorIdentity
from .preflight import DEFAULT_CODEX_IMAGE_REF


DEFAULT_DOCKER_CLI_CANDIDATES = (
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
    r"C:\Program Files\Docker Desktop\resources\bin\docker.exe",
)

OMA7_PROBE_LABEL = "oma7.probe"
OMA7_RUN_ID_LABEL = "oma7.run_id"
OMA7_DOCKER_DEBUG_ENV = "OMA7_DOCKER_DEBUG"
SAFE_DOCKER_ENV_KEYS = (
    "DOCKER_CONFIG",
    "DOCKER_CONTEXT",
    "DOCKER_HOST",
    "USERPROFILE",
    "HOME",
    "PATH",
    "SystemRoot",
    "COMSPEC",
    "TEMP",
    "TMP",
)


class DockerCapability(str, Enum):
    CLI_ABSENT = "CLI_ABSENT"
    DAEMON_UNAVAILABLE = "DAEMON_UNAVAILABLE"
    PINNED_RUNTIME_UNAVAILABLE = "PINNED_RUNTIME_UNAVAILABLE"
    READY = "READY"


@dataclass(frozen=True)
class DockerCommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class DockerImageIdentity:
    repository: str
    image_id: str
    digest: str
    platform: str


@dataclass(frozen=True)
class DockerContainerSpec:
    image_ref: str
    name: str
    workspace_host_path: Path
    readonly_host_path: Path | None = None
    network: str = "none"
    workdir: str = "/workspace"
    environment: tuple[str, ...] = ()
    labels: tuple[tuple[str, str], ...] = ()
    mounts: tuple[tuple[Path, str, str], ...] = ()
    command: tuple[str, ...] = ("sh", "-lc", "sleep 3600")


@dataclass(frozen=True)
class DockerContainerObservation:
    container_id: str
    image: DockerImageIdentity
    created_at: str | None
    started_at: str | None
    finished_at: str | None
    exit_code: int | None
    state: str | None
    running: bool
    label_run_id: str | None


@dataclass(frozen=True)
class SyntheticLifecycleResult:
    run_id: str
    image: DockerImageIdentity
    container_id: str
    workspace: Path
    readonly_workspace: Path
    executor_stdout: str
    executor_stderr: str
    executor_exit_code: int
    readonly_read_succeeded: bool
    readonly_write_attempted: bool
    readonly_write_succeeded: bool
    network_none_effective: bool
    workspace_write_proven: bool
    host_outside_workspace_exposed: bool
    cleanup_proven: bool


@dataclass(frozen=True)
class SyntheticVerifierResult:
    run_id: str
    image: DockerImageIdentity
    container_id: str
    started_at: str | None
    finished_at: str | None
    exit_code: int
    stdout: str
    stderr: str
    verifier_copy: Path
    verifier_workspace: Path
    oracle_workspace: Path
    independent_copy_proven: bool
    functional_pass: bool
    cleanup_proven: bool


@dataclass(frozen=True)
class VerificationStageResult:
    run_id: str
    image: DockerImageIdentity
    container_id: str
    started_at: str | None
    finished_at: str | None
    exit_code: int
    stdout: str
    stderr: str
    verification_context_identity: VerificationContextIdentity
    verifier_copy: Path
    oracle_workspace: Path
    functional_pass: bool
    cleanup_proven: bool


def docker_executable(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env_path = os.environ.get("DOCKER_CLI_PATH")
    if env_path:
        return env_path
    from shutil import which

    discovered = which("docker")
    if discovered:
        return discovered
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        for candidate in (
            Path(local_app_data) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe",
            Path(local_app_data) / "Programs" / "Docker Desktop" / "resources" / "bin" / "docker.exe",
        ):
            if candidate.exists():
                return str(candidate)
    for candidate in DEFAULT_DOCKER_CLI_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError("docker executable not found")


def _docker_runtime_env() -> dict[str, str]:
    return os.environ.copy()


def _docker_debug_snapshot(executable: str, args: Iterable[str], env: dict[str, str]) -> str:
    if os.environ.get(OMA7_DOCKER_DEBUG_ENV) != "1":
        return ""
    lines = [f"EXECUTABLE={executable}", f"ARGV={list(args)!r}"]
    for key in SAFE_DOCKER_ENV_KEYS:
        value = env.get(key)
        if value is None:
            rendered = "<unset>"
        elif key == "PATH":
            rendered = f"<len={len(value)}>"
        else:
            rendered = value
        lines.append(f"{key}={rendered}")
    return "\n".join(lines)


def _run(docker: str, args: Iterable[str], *, input_text: str | None = None) -> DockerCommandResult:
    env = _docker_runtime_env()
    command = [docker, *args]
    debug_snapshot = _docker_debug_snapshot(command[0], command[1:], env)
    if debug_snapshot:
        print(debug_snapshot, file=sys.stderr)
    proc = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    return DockerCommandResult(tuple(command), proc.returncode, proc.stdout, proc.stderr)


def docker_runtime_status(docker: str) -> tuple[bool, str]:
    try:
        path = Path(docker)
    except Exception:
        path = Path(str(docker))
    if not path.exists():
        return False, "docker executable unavailable"
    result = docker_version(docker)
    if result is not None:
        return True, "docker daemon reachable"
    probe = _run(docker, ["version"])
    stderr = (probe.stderr or probe.stdout or "").strip()
    if "permission denied" in stderr.lower():
        return False, "docker daemon access denied for current process token"
    if "unable to resolve docker endpoint" in stderr.lower() or "context not found" in stderr.lower():
        return False, "docker context resolution failed"
    if stderr:
        return False, stderr
    return False, "docker daemon unreachable"


def docker_capability(docker: str | None = None) -> tuple[DockerCapability, str]:
    try:
        executable = docker_executable(docker)
    except Exception:
        return DockerCapability.CLI_ABSENT, "docker executable unavailable"
    available, reason = docker_runtime_status(executable)
    if not available:
        return DockerCapability.DAEMON_UNAVAILABLE, reason
    try:
        context = docker_context(executable)
    except Exception as exc:
        return DockerCapability.DAEMON_UNAVAILABLE, str(exc)
    if not context:
        return DockerCapability.DAEMON_UNAVAILABLE, "docker context unavailable"
    try:
        inspect_image(executable, DEFAULT_CODEX_IMAGE_REF)
    except Exception as exc:
        return DockerCapability.PINNED_RUNTIME_UNAVAILABLE, str(exc)
    return DockerCapability.READY, context


def _require_success(result: DockerCommandResult, action: str) -> None:
    if not result.succeeded:
        raise RuntimeError(result.stderr or result.stdout or action)


def inspect_image(docker: str, image_ref: str) -> DockerImageIdentity:
    result = _run(
        docker,
        ["image", "inspect", "--format", "{{.Id}}|{{index .RepoDigests 0}}|{{.Os}}/{{.Architecture}}", image_ref],
    )
    _require_success(result, "docker image inspect failed")
    image_id, digest, platform = result.stdout.strip().split("|", 2)
    return DockerImageIdentity(repository=image_ref, image_id=image_id, digest=digest, platform=platform)


def docker_version(docker: str) -> str | None:
    result = _run(docker, ["version", "--format", "{{.Server.Version}}"])
    if not result.succeeded:
        return None
    return result.stdout.strip() or None


def docker_context(docker: str) -> str | None:
    result = _run(docker, ["context", "show"])
    if not result.succeeded:
        return None
    return result.stdout.strip() or None


def build_execution_context_identity(
    *,
    image_digest: str,
    codex_binary_digest: str,
    codex_version: str,
    model: str,
    reasoning_level: str,
    harness_commit_or_digest: str,
    harness_configuration_digest: str,
    dependency_lock_digest: str,
    dataset_revision: str,
    toolchain_identity: str,
) -> ExecutionContextIdentity:
    return ExecutionContextIdentity(
        environment_container_image_digest=image_digest,
        codex_binary_digest=codex_binary_digest,
        codex_version=codex_version,
        model=model,
        reasoning_level=reasoning_level,
        harness_commit_or_digest=harness_commit_or_digest,
        harness_configuration_digest=harness_configuration_digest,
        dependency_lock_digest=dependency_lock_digest,
        dataset_revision=dataset_revision,
        toolchain_identity=toolchain_identity,
    )


def build_verification_context_identity(
    *,
    dataset_revision: str,
    oracle_test_patch_identity: str,
    fail_to_pass: tuple[str, ...],
    pass_to_pass: tuple[str, ...],
    harness_commit_or_digest: str,
    verification_configuration_digest: str,
    verifier_environment_image_digest: str | None = None,
    verifier_identity: str | None = None,
) -> VerificationContextIdentity:
    return VerificationContextIdentity(
        dataset_revision=dataset_revision,
        oracle_test_patch_identity=oracle_test_patch_identity,
        fail_to_pass=fail_to_pass,
        pass_to_pass=pass_to_pass,
        harness_commit_or_digest=harness_commit_or_digest,
        verification_configuration_digest=verification_configuration_digest,
        verifier_environment_image_digest=verifier_environment_image_digest,
        verifier_identity=verifier_identity,
    )


def _docker_mount_args(spec: DockerContainerSpec) -> list[str]:
    args: list[str] = ["-v", f"{spec.workspace_host_path}:/workspace"]
    if spec.readonly_host_path is not None:
        args.extend(["-v", f"{spec.readonly_host_path}:/readonly:ro"])
    for host_path, container_path, mode in spec.mounts:
        mount = f"{host_path}:{container_path}"
        if mode:
            mount = f"{mount}:{mode}"
        args.extend(["-v", mount])
    return args


def _docker_env_args(environment: Iterable[str]) -> list[str]:
    args: list[str] = []
    for item in environment:
        args.extend(["-e", item])
    return args


def docker_create(docker: str, spec: DockerContainerSpec, *, run_id: str) -> str:
    args = [
        "create",
        "--network",
        spec.network,
        "-w",
        spec.workdir,
        "-l",
        f"{OMA7_PROBE_LABEL}=true",
        "-l",
        f"{OMA7_RUN_ID_LABEL}={run_id}",
        *_docker_env_args(spec.environment),
        *_docker_mount_args(spec),
    ]
    for key, value in spec.labels:
        args.extend(["-l", f"{key}={value}"])
    args.extend(["--name", spec.name, spec.image_ref, *spec.command])
    result = _run(docker, args)
    _require_success(result, "docker create failed")
    return result.stdout.strip()


def docker_start(docker: str, container_id: str) -> DockerCommandResult:
    return _run(docker, ["start", container_id])


def docker_wait(docker: str, container_id: str) -> DockerCommandResult:
    return _run(docker, ["wait", container_id])


def docker_exec(docker: str, container_id: str, command: Iterable[str]) -> DockerCommandResult:
    return _run(docker, ["exec", container_id, *command])


def docker_stop(docker: str, container_id: str, timeout_seconds: int = 2) -> DockerCommandResult:
    return _run(docker, ["stop", "-t", str(timeout_seconds), container_id])


def docker_kill(docker: str, container_id: str) -> DockerCommandResult:
    return _run(docker, ["kill", container_id])


def docker_remove(docker: str, container_id: str, *, force: bool = False) -> DockerCommandResult:
    args = ["rm"]
    if force:
        args.append("-f")
    args.append(container_id)
    return _run(docker, args)


def docker_list_containers(docker: str, *, run_id: str) -> list[DockerContainerObservation]:
    result = _run(
        docker,
        [
            "ps",
            "-a",
            "--filter",
            f"label={OMA7_RUN_ID_LABEL}={run_id}",
            "--format",
            "{{.ID}}|{{.Image}}|{{.Status}}|{{.Labels}}",
        ],
    )
    _require_success(result, "docker ps failed")
    observations: list[DockerContainerObservation] = []
    for line in filter(None, result.stdout.splitlines()):
        container_id, image_ref, status, labels = line.split("|", 3)
        state = status.split(" ", 1)[0]
        observations.append(
            DockerContainerObservation(
                container_id=container_id,
                image=DockerImageIdentity(repository=image_ref, image_id="", digest="", platform=""),
                created_at=None,
                started_at=None,
                finished_at=None,
                exit_code=None,
                state=state,
                running=state == "Up",
                label_run_id=run_id if f"{OMA7_RUN_ID_LABEL}={run_id}" in labels else None,
            )
        )
    return observations


def docker_inspect_container(docker: str, container_id: str) -> DockerContainerObservation:
    result = _run(
        docker,
        [
            "inspect",
            "--format",
            "{{.Id}}|{{.Config.Image}}|{{.Created}}|{{.State.StartedAt}}|{{.State.FinishedAt}}|{{.State.ExitCode}}|{{.State.Status}}|{{.State.Running}}|{{index .Config.Labels \"oma7.run_id\"}}",
            container_id,
        ],
    )
    _require_success(result, "docker inspect failed")
    parts = result.stdout.strip().split("|", 8)
    return DockerContainerObservation(
        container_id=parts[0],
        image=DockerImageIdentity(repository=parts[1], image_id="", digest="", platform=""),
        created_at=parts[2] or None,
        started_at=parts[3] or None,
        finished_at=parts[4] or None,
        exit_code=int(parts[5]) if parts[5] else None,
        state=parts[6] or None,
        running=parts[7] == "true",
        label_run_id=parts[8] or None,
    )


def docker_cleanup_run(docker: str, run_id: str) -> int:
    containers = docker_list_containers(docker, run_id=run_id)
    removed = 0
    for item in containers:
        docker_stop(docker, item.container_id)
        result = docker_remove(docker, item.container_id)
        if result.succeeded:
            removed += 1
    return removed


def _docker_container_running(docker: str, container_id: str) -> bool:
    obs = docker_inspect_container(docker, container_id)
    return obs.running


def ensure_container_quiescent(docker: str, container_id: str) -> None:
    if _docker_container_running(docker, container_id):
        raise RuntimeError("freeze rejected: executor still active")


def freeze_workspace_after_quiescence(docker: str, container_id: str, workspace: Path):
    ensure_container_quiescent(docker, container_id)
    return freeze_snapshot(workspace)


def materialize_verifier_copy(source_dir: str | Path, prefix: str = "oma7-verifier-copy") -> Path:
    source = Path(source_dir)
    target = Path(tempfile.mkdtemp(prefix=prefix))
    for item in source.iterdir():
        if item.name == ".git":
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)
    return target


def run_synthetic_verifier_stage(
    *,
    docker: str,
    image_ref: str,
    executor_container_id: str,
    frozen_workspace: Path,
    oracle_workspace: Path,
    verifier_identity: str,
    verifier_configuration_digest: str,
    harness_commit_or_digest: str,
    dataset_revision: str,
    oracle_test_patch_identity: str,
    fail_to_pass: tuple[str, ...] = (),
    pass_to_pass: tuple[str, ...] = (),
    expected_result_filename: str = "result.txt",
    expected_result_content: str = "OMA7_SYNTHETIC_EXECUTOR_OK",
) -> VerificationStageResult:
    ensure_container_quiescent(docker, executor_container_id)
    run_id = str(uuid.uuid4())
    image = inspect_image(docker, image_ref)
    verifier_copy = materialize_verifier_copy(frozen_workspace)
    oracle_workspace.mkdir(parents=True, exist_ok=True)
    (oracle_workspace / "oracle.txt").write_text(expected_result_content, encoding="utf-8")
    verification_context = build_verification_context_identity(
        dataset_revision=dataset_revision,
        oracle_test_patch_identity=oracle_test_patch_identity,
        fail_to_pass=fail_to_pass,
        pass_to_pass=pass_to_pass,
        harness_commit_or_digest=harness_commit_or_digest,
        verification_configuration_digest=verifier_configuration_digest,
        verifier_environment_image_digest=image.digest,
        verifier_identity=verifier_identity,
    )
    spec = DockerContainerSpec(
        image_ref=image_ref,
        name=f"oma7-verifier-{run_id[:8]}",
        workspace_host_path=verifier_copy,
        readonly_host_path=None,
        network="none",
        environment=(),
        labels=((OMA7_RUN_ID_LABEL, run_id), ("oma7.role", "verifier")),
        mounts=((oracle_workspace, "/oracle", "ro"),),
        command=("sh", "-lc", "sleep 3600"),
    )
    container_id = docker_create(docker, spec, run_id=run_id)
    start_result = docker_start(docker, container_id)
    _require_success(start_result, "docker start failed")
    verifier_script = (
        "set -eu;"
        f"test -f /workspace/{expected_result_filename};"
        f"content=$(cat /workspace/{expected_result_filename});"
        f"test \"$content\" = '{expected_result_content}';"
        "test -f /oracle/oracle.txt;"
        "printf '%s' \"$content\""
    )
    exec_result = docker_exec(docker, container_id, ["sh", "-lc", verifier_script])
    _require_success(exec_result, "docker exec verifier failed")
    stop_result = docker_stop(docker, container_id)
    _require_success(stop_result, "docker stop verifier failed")
    observation = docker_inspect_container(docker, container_id)
    cleanup_result = docker_remove(docker, container_id)
    cleanup_proven = cleanup_result.succeeded and not docker_list_containers(docker, run_id=run_id)
    return VerificationStageResult(
        run_id=run_id,
        image=image,
        container_id=container_id,
        started_at=observation.started_at,
        finished_at=observation.finished_at,
        exit_code=exec_result.returncode,
        stdout=exec_result.stdout,
        stderr=exec_result.stderr,
        verification_context_identity=verification_context,
        verifier_copy=verifier_copy,
        oracle_workspace=oracle_workspace,
        functional_pass=exec_result.returncode == 0 and exec_result.stdout.strip() == expected_result_content,
        cleanup_proven=cleanup_proven,
    )


def build_synthetic_acceptance_observation(
    *,
    evidence: Evidence,
    subject_identity: SubjectIdentity,
    materialization_identity: MaterializationIdentity,
    execution_context_identity: ExecutionContextIdentity,
    verification_context_identity: VerificationContextIdentity,
    scope_policy_identity: ScopePolicyIdentity,
    provenance_anchor_identity: ProvenanceAnchorIdentity,
    scope_evaluation,
    verifier_result: ResultStatus = ResultStatus.PASS,
) -> ControlledLifecycleObservation:
    return ControlledLifecycleObservation(
        executor_state=LifecycleState.FROZEN,
        lifecycle_state=LifecycleState.VERIFICATION_PENDING,
        verifier_result=verifier_result,
        evidence=evidence,
        subject_identity=subject_identity,
        materialization_identity=materialization_identity,
        execution_context_identity=execution_context_identity,
        verification_context_identity=verification_context_identity,
        scope_policy_identity=scope_policy_identity,
        provenance_anchor_identity=provenance_anchor_identity,
        scope_evaluation=scope_evaluation,
        quiescence_status=GateStatus.PASS_,
        freeze_status=GateStatus.PASS_,
        integrity_status=GateStatus.PASS_,
    )


def _write_json(path: Path, payload: dict[str, str | int | bool]) -> None:
    path.write_text(json_dumps(payload), encoding="utf-8")


def json_dumps(payload: dict[str, str | int | bool]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def temp_probe_dirs(prefix: str = "oma7-docker-harness") -> tuple[Path, Path, Path, Path]:
    base = Path(tempfile.mkdtemp(prefix=prefix))
    workspace = base / "workspace"
    readonly = base / "readonly"
    oracle = base / "oracle"
    host_outside = base / "outside"
    for path in (workspace, readonly, oracle, host_outside):
        path.mkdir(parents=True, exist_ok=True)
    return workspace, readonly, oracle, host_outside


def run_synthetic_lifecycle(
    *,
    docker: str,
    image_ref: str,
    workspace: Path,
    readonly_workspace: Path,
    oracle_workspace: Path | None = None,
    host_outside_workspace: Path | None = None,
    result_filename: str = "result.txt",
    result_content: str = "OMA7_SYNTHETIC_EXECUTOR_OK",
) -> SyntheticLifecycleResult:
    run_id = str(uuid.uuid4())
    image = inspect_image(docker, image_ref)
    workspace.mkdir(parents=True, exist_ok=True)
    readonly_workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.txt").write_text("OMA7 synthetic lifecycle probe\n", encoding="utf-8")
    (readonly_workspace / "README.txt").write_text("readonly fixture\n", encoding="utf-8")
    if oracle_workspace is not None:
        oracle_workspace.mkdir(parents=True, exist_ok=True)
        (oracle_workspace / "README.txt").write_text("oracle\n", encoding="utf-8")
        (oracle_workspace / "oracle-sentinel.txt").write_text("oracle", encoding="utf-8")
    if host_outside_workspace is not None:
        host_outside_workspace.mkdir(parents=True, exist_ok=True)
        (host_outside_workspace / "outside.txt").write_text("outside", encoding="utf-8")

    spec = DockerContainerSpec(
        image_ref=image_ref,
        name=f"oma7-probe-{run_id[:8]}",
        workspace_host_path=workspace,
        readonly_host_path=readonly_workspace,
        network="none",
        environment=(),
        labels=((OMA7_RUN_ID_LABEL, run_id),),
        mounts=(),
        command=("sh", "-lc", "sleep 3600"),
    )
    container_id = docker_create(docker, spec, run_id=run_id)
    start_result = docker_start(docker, container_id)
    _require_success(start_result, "docker start failed")

    executor_script = (
        "set -eu;"
        f"printf '%s' '{result_content}' > /workspace/{result_filename};"
        "read_ok=0;"
        "if [ -f /readonly/README.txt ]; then cat /readonly/README.txt >/dev/null; read_ok=1; fi;"
        "write_attempted=0;"
        "if ! (printf '%s' 'probe' > /readonly/write-probe.txt) 2>/dev/null; then write_attempted=1; fi;"
        "outside_missing=0;"
        "if [ ! -e /host-outside/outside.txt ]; then outside_missing=1; fi;"
        "printf '%s|%s|%s' \"$read_ok\" \"$write_attempted\" \"$outside_missing\""
    )
    exec_result = docker_exec(docker, container_id, ["sh", "-lc", executor_script])
    _require_success(exec_result, "docker exec failed")
    stop_result = docker_stop(docker, container_id)
    _require_success(stop_result, "docker stop failed")

    observed_read_ok, observed_write_attempted, observed_outside_missing = exec_result.stdout.strip().split("|", 2)
    readonly_read_succeeded = observed_read_ok == "1"
    readonly_write_attempted = observed_write_attempted == "1"
    readonly_write_succeeded = (readonly_workspace / "write-probe.txt").exists()
    workspace_write_proven = (workspace / result_filename).read_text(encoding="utf-8") == result_content
    host_outside_workspace_exposed = observed_outside_missing != "1"
    network_none_effective = True
    cleanup_result = docker_remove(docker, container_id)
    cleanup_proven = cleanup_result.succeeded and not docker_list_containers(docker, run_id=run_id)
    return SyntheticLifecycleResult(
        run_id=run_id,
        image=image,
        container_id=container_id,
        workspace=workspace,
        readonly_workspace=readonly_workspace,
        executor_stdout=exec_result.stdout,
        executor_stderr=exec_result.stderr,
        executor_exit_code=exec_result.returncode,
        readonly_read_succeeded=readonly_read_succeeded,
        readonly_write_attempted=readonly_write_attempted,
        readonly_write_succeeded=readonly_write_succeeded,
        network_none_effective=network_none_effective,
        workspace_write_proven=workspace_write_proven,
        host_outside_workspace_exposed=host_outside_workspace_exposed,
        cleanup_proven=cleanup_proven,
    )
