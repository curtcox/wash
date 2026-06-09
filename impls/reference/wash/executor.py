"""Command execution: interpreter resolution and pipeline evaluation."""

from __future__ import annotations

import fnmatch
import os
import selectors
import subprocess
from dataclasses import dataclass
from pathlib import Path

from wash.filesystem import implied_cat_bytes
from wash.metadata import CommandMetadata, map_exit_status
from wash.parser import CommandStage, PipelineParse, RawCommandParse


class ExecutionError(Exception):
    def __init__(self, message: str, *, status: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class ExecRule:
    pattern: str
    interpreter: str
    extra_args: list[str]


@dataclass
class StageResult:
    name: str
    exit_code: int
    stdout: bytes
    stderr: bytes
    http_status: int


@dataclass
class PipelineResult:
    stdout: bytes
    stderr: bytes
    content_type: str
    stages: list[StageResult]
    pipeline_description: str
    source_path: str | None
    final_command: str | None = None
    failing_stage: StageResult | None = None
    http_status: int = 200


@dataclass
class ExecConfig:
    rules: list[ExecRule]
    malformed: bool = False
    malformed_reason: str | None = None


def load_exec_rules(root: Path) -> ExecConfig:
    exec_file = root / "exec"
    rules: list[ExecRule] = []
    if not exec_file.is_file():
        return ExecConfig(rules)
    for line in exec_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] == "#":
            continue
        parts = stripped.split()
        if len(parts) < 2:
            return ExecConfig(
                rules,
                malformed=True,
                malformed_reason=f"malformed exec rule: {line!r}",
            )
        rules.append(
            ExecRule(
                pattern=parts[0],
                interpreter=parts[1],
                extra_args=parts[2:],
            )
        )
    return ExecConfig(rules)


def _has_glob(pattern: str) -> bool:
    return any(ch in pattern for ch in "*?[]")


def _rule_matches(rule: ExecRule, command_path: Path, command_dir: Path) -> bool:
    basename = command_path.name
    if not _has_glob(rule.pattern):
        return basename == rule.pattern
    rel = command_path.relative_to(command_dir).as_posix()
    return fnmatch.fnmatch(basename, rule.pattern) or fnmatch.fnmatch(rel, rule.pattern)


def resolve_invocation(
    command_path: Path,
    command_dirs: list[Path],
    exec_config: ExecConfig,
) -> list[str]:
    if exec_config.malformed:
        raise ExecutionError(
            exec_config.malformed_reason or "malformed exec rules",
            status=500,
        )

    rules = exec_config.rules
    if os.access(command_path, os.X_OK) and command_path.is_file():
        return [str(command_path)]

    command_dir: Path | None = None
    for d in command_dirs:
        try:
            command_path.relative_to(d)
            command_dir = d
            break
        except ValueError:
            continue

    if command_dir is None:
        command_dir = command_path.parent

    for rule in rules:
        if _rule_matches(rule, command_path, command_dir):
            if rule.interpreter == "__wash_missing_interpreter__":
                raise ExecutionError(
                    f"unresolved interpreter for command {command_path.name}",
                    status=500,
                )
            return [rule.interpreter, *rule.extra_args, str(command_path)]

    if command_path.is_file():
        return [str(command_path)]

    raise ExecutionError(
        f"could not resolve interpreter for command {command_path.name}",
        status=500,
    )


def _stderr_merge_enabled(stage: CommandStage) -> bool:
    return stage.stderr_merge_boundary or stage.metadata.stderr_mode == "merge"


def _run_process(
    argv: list[str],
    *,
    cwd: Path,
    stdin_data: bytes | None,
    merge_stderr: bool,
) -> tuple[int, bytes, bytes]:
    stderr_opt = subprocess.STDOUT if merge_stderr else subprocess.PIPE
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_opt,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )
    assert proc.stdin is not None
    if stdin_data is not None:
        proc.stdin.write(stdin_data)
    proc.stdin.close()

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []

    if merge_stderr:
        assert proc.stdout is not None
        stdout_chunks.append(proc.stdout.read())
    else:
        sel = selectors.DefaultSelector()
        if proc.stdout is not None:
            sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
        if proc.stderr is not None:
            sel.register(proc.stderr, selectors.EVENT_READ, "stderr")
        while sel.get_map():
            for key, _ in sel.select(timeout=0.1):
                chunk = key.fileobj.read(65536)  # type: ignore[union-attr]
                if not chunk:
                    sel.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    stdout_chunks.append(chunk)
                else:
                    stderr_chunks.append(chunk)
        if proc.stdout is not None:
            rest = proc.stdout.read()
            if rest:
                stdout_chunks.append(rest)
        if proc.stderr is not None:
            rest = proc.stderr.read()
            if rest:
                stderr_chunks.append(rest)

    exit_code = proc.wait()
    return exit_code, b"".join(stdout_chunks), b"".join(stderr_chunks)


def execute_raw_command(
    raw: RawCommandParse,
    *,
    root: Path,
    command_dirs: list[Path],
    exec_config: ExecConfig,
    method: str,
    body: bytes,
) -> PipelineResult:
    stage = raw.stage
    invocation = resolve_invocation(stage.command_path, command_dirs, exec_config)
    invocation = invocation + [raw.raw_suffix]
    stdin_data = body if body else None
    exit_code, stdout, stderr = _run_process(
        invocation,
        cwd=root,
        stdin_data=stdin_data,
        merge_stderr=_stderr_merge_enabled(stage),
    )
    http_status = map_exit_status(stage.metadata, exit_code)
    stage_result = StageResult(
        name=stage.name,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        http_status=http_status,
    )
    content_type = stage.metadata.mime or "text/plain"
    return PipelineResult(
        stdout=stdout,
        stderr=stderr,
        content_type=content_type,
        stages=[stage_result],
        pipeline_description=f"{stage.name} {raw.raw_suffix}".strip(),
        source_path=None,
        final_command=stage.name,
        failing_stage=stage_result if http_status >= 400 else None,
        http_status=http_status,
    )


def execute_pipeline(
    pipeline: PipelineParse,
    *,
    root: Path,
    command_dirs: list[Path],
    exec_config: ExecConfig,
    body: bytes,
    symlink_policy: str = "reject-escaping",
    case_sensitive: bool = True,
) -> PipelineResult:
    stages = pipeline.stages
    if not stages:
        raise ExecutionError("empty pipeline")

    stdin_data: bytes | None = None
    if pipeline.input_suffix_raw:
        try:
            stdin_data = implied_cat_bytes(
                root,
                pipeline.input_suffix_raw,
                symlink_policy=symlink_policy,
                case_sensitive=case_sensitive,
            )
        except FileNotFoundError as exc:
            raise ExecutionError(str(exc), status=404) from exc
        except IsADirectoryError as exc:
            raise ExecutionError(str(exc), status=400) from exc
    elif body:
        stdin_data = body

    data_flow_stages = list(reversed(stages))
    stage_results: list[StageResult] = []
    current_input = stdin_data

    for i, stage in enumerate(data_flow_stages):
        invocation = resolve_invocation(stage.command_path, command_dirs, exec_config)
        invocation = invocation + stage.argv
        merge = _stderr_merge_enabled(stage)
        exit_code, stdout, stderr = _run_process(
            invocation,
            cwd=root,
            stdin_data=current_input,
            merge_stderr=merge,
        )
        http_status = map_exit_status(stage.metadata, exit_code)
        result = StageResult(
            name=stage.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            http_status=http_status,
        )
        stage_results.append(result)
        current_input = stdout

    first_fail = _first_failing_in_url_order(stages, stage_results)
    if first_fail is not None:
        return PipelineResult(
            stdout=first_fail.stdout,
            stderr=first_fail.stderr,
            content_type=_final_content_type(stages),
            stages=stage_results,
            pipeline_description=pipeline.pipeline_description,
            source_path=pipeline.source_path,
            final_command=stages[0].name if stages else None,
            failing_stage=first_fail,
            http_status=first_fail.http_status,
        )

    final_stage = stages[0]
    content_type = final_stage.metadata.mime or "text/plain"
    return PipelineResult(
        stdout=current_input or b"",
        stderr=b"",
        content_type=content_type,
        stages=stage_results,
        pipeline_description=pipeline.pipeline_description,
        source_path=pipeline.source_path,
        final_command=stages[0].name if stages else None,
        failing_stage=None,
        http_status=200,
    )


def _first_failing_in_url_order(
    url_stages: list[CommandStage],
    data_flow_results: list[StageResult],
) -> StageResult | None:
    by_name = {r.name: r for r in data_flow_results}
    for stage in url_stages:
        result = by_name.get(stage.name)
        if result and result.http_status >= 400:
            return result
    return None


def _final_content_type(stages: list[CommandStage]) -> str:
    if stages:
        return stages[0].metadata.mime or "text/plain"
    return "text/plain"
