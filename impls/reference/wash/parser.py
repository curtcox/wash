"""URL pipeline parsing per pipeline_parsing.md."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qsl

from wash.filesystem import (
    FilesystemResource,
    percent_decode_segment,
    resolve_under_root,
    split_raw_target,
    try_exact_filesystem,
)
from wash.metadata import CommandMetadata, load_metadata


class ParseError(Exception):
    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class ParsedSegment:
    raw: str
    name: str
    query_items: list[tuple[str, str]]
    stderr_merge: bool


@dataclass
class CommandStage:
    name: str
    command_path: Path
    argv: list[str]
    metadata: CommandMetadata
    stderr_merge_boundary: bool
    raw_segment: str
    argv_from_query: bool = False


@dataclass
class PipelineParse:
    stages: list[CommandStage]
    input_suffix_raw: list[str] | None
    pipeline_description: str = ""
    source_path: str | None = None


@dataclass
class RawCommandParse:
    stage: CommandStage
    raw_suffix: str


@dataclass
class FilesystemParse:
    resource: FilesystemResource


@dataclass
class NotFoundParse:
    pass


ParseResult = PipelineParse | RawCommandParse | FilesystemParse | NotFoundParse


def parse_segment(raw: str) -> ParsedSegment:
    stderr_merge = False
    body = raw
    if body.startswith("&"):
        stderr_merge = True
        body = body[1:]

    if "?" in body:
        name_part, query_part = body.split("?", 1)
    else:
        name_part, query_part = body, ""

    name = percent_decode_segment(name_part, for_filesystem=False)
    query_items: list[tuple[str, str]] = []
    if query_part:
        for key, value in parse_qsl(query_part, keep_blank_values=True):
            query_items.append((key, value))

    return ParsedSegment(
        raw=raw,
        name=name,
        query_items=query_items,
        stderr_merge=stderr_merge,
    )


def core_argv_from_query(query_items: list[tuple[str, str]]) -> list[str] | None:
    args = [value for key, value in query_items if key == "arg"]
    if not args and any(key == "arg" for key, _ in query_items):
        return []
    if not args:
        return None
    return [percent_decode_segment(a, for_filesystem=False) for a in args]


def load_command_path(root: Path) -> list[Path]:
    path_file = root / "env" / "path"
    dirs: list[Path] = []
    if not path_file.is_file():
        return dirs
    for line in path_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        p = Path(stripped)
        if not p.is_absolute():
            p = (root / p).resolve()
        else:
            p = p.resolve()
        if p.is_dir():
            dirs.append(p)
    return dirs


def resolve_command(
    name: str,
    command_dirs: list[Path],
    *,
    case_sensitive: bool = True,
) -> Path | None:
    for directory in command_dirs:
        candidate = directory / name
        if candidate.exists() and candidate.is_file():
            return candidate
        if not case_sensitive and directory.is_dir():
            for entry in directory.iterdir():
                if entry.name.lower() == name.lower() and entry.is_file():
                    return entry
    return None


def is_command(
    name: str,
    command_dirs: list[Path],
    *,
    case_sensitive: bool = True,
) -> bool:
    return (
        resolve_command(name, command_dirs, case_sensitive=case_sensitive) is not None
    )


def _remaining_raw_suffix(raw_segments: list[str], start: int) -> str:
    if start >= len(raw_segments):
        return ""
    return "/".join(raw_segments[start:])


def _format_pipeline(stages: list[CommandStage], input_suffix: list[str] | None) -> str:
    parts: list[str] = []
    if input_suffix:
        parts.append(f"cat {'/'.join(input_suffix)}")
    for stage in reversed(stages):
        cmd = stage.name
        if stage.argv:
            cmd += " " + " ".join(stage.argv)
        parts.append(cmd)
    return " | ".join(parts)


def parse_request(
    method: str,
    raw_target: str,
    root: Path,
    *,
    command_dirs: list[Path] | None = None,
    case_sensitive: bool = True,
    symlink_policy: str = "reject-escaping",
    resolve_command_fn: Callable[..., Path | None] | None = None,
) -> ParseResult:
    if command_dirs is None:
        command_dirs = load_command_path(root)

    resolve = resolve_command_fn or (
        lambda name, dirs: resolve_command(name, dirs, case_sensitive=case_sensitive)
    )

    raw_target = raw_target.split("#", 1)[0]
    if "?" in raw_target and "/" in raw_target:
        pass
    segments = split_raw_target(raw_target)

    fs = try_exact_filesystem(
        root,
        segments,
        symlink_policy=symlink_policy,
        case_sensitive=case_sensitive,
    )
    if fs is not None:
        return FilesystemParse(fs)

    if not segments:
        return NotFoundParse()

    first = parse_segment(segments[0])
    first_path = resolve(first.name, command_dirs)
    if first_path is None:
        return NotFoundParse()

    stages: list[CommandStage] = []
    idx = 0

    while idx < len(segments):
        seg = parse_segment(segments[idx])
        cmd_path = resolve(seg.name, command_dirs)
        if cmd_path is None:
            if not stages:
                return NotFoundParse()
            break

        meta = load_metadata(root, seg.name)
        if meta.invalid:
            raise ParseError(
                f"malformed metadata for command {seg.name}: {meta.malformed_reason}",
                status=500,
            )

        if meta.parse_mode == "raw":
            if idx != 0:
                raise ParseError(
                    f"parse-mode raw on {seg.name} is only valid in leftmost position",
                    status=500,
                )
            raw_suffix = _remaining_raw_suffix(segments, idx + 1)
            stage = CommandStage(
                name=seg.name,
                command_path=cmd_path,
                argv=[],
                metadata=meta,
                stderr_merge_boundary=seg.stderr_merge,
                raw_segment=seg.raw,
            )
            return RawCommandParse(stage=stage, raw_suffix=raw_suffix)

        query_argv = core_argv_from_query(seg.query_items)
        argv_from_query = query_argv is not None
        if query_argv is not None:
            argv = query_argv
            idx += 1
        elif meta.arity == "*":
            argv = [
                percent_decode_segment(s, for_filesystem=False)
                for s in segments[idx + 1 :]
            ]
            idx = len(segments)
            stages.append(
                CommandStage(
                    name=seg.name,
                    command_path=cmd_path,
                    argv=argv,
                    metadata=meta,
                    stderr_merge_boundary=seg.stderr_merge,
                    raw_segment=seg.raw,
                    argv_from_query=argv_from_query,
                )
            )
            pipeline = PipelineParse(
                stages=stages,
                input_suffix_raw=None,
                pipeline_description=_format_pipeline(stages, None),
            )
            return pipeline
        else:
            arity = meta.arity if isinstance(meta.arity, int) else 0
            if arity > 0 and idx + arity >= len(segments):
                raise ParseError(
                    f"command {seg.name} expects arity {arity} but insufficient path segments",
                )
            argv = []
            for offset in range(1, arity + 1):
                arg_seg = parse_segment(segments[idx + offset])
                if any(key == "arg" for key, _ in arg_seg.query_items):
                    if resolve(arg_seg.name, command_dirs) is None:
                        raise ParseError(
                            f"core arg query on non-command segment {arg_seg.name!r}",
                        )
                argv.append(
                    percent_decode_segment(segments[idx + offset], for_filesystem=False)
                )
            idx += 1 + arity

        stages.append(
            CommandStage(
                name=seg.name,
                command_path=cmd_path,
                argv=argv,
                metadata=meta,
                stderr_merge_boundary=seg.stderr_merge,
                raw_segment=seg.raw,
                argv_from_query=argv_from_query,
            )
        )

        if idx >= len(segments):
            break

        next_seg = parse_segment(segments[idx])
        if resolve(next_seg.name, command_dirs) is not None:
            continue

        if any(key == "arg" for key, _ in next_seg.query_items):
            raise ParseError(
                f"core arg query on non-command segment {next_seg.name!r}",
            )

        remaining = segments[idx:]
        for later in remaining[1:]:
            later_seg = parse_segment(later)
            if resolve(later_seg.name, command_dirs) is not None:
                raise ParseError(
                    f"unexpected segment {next_seg.name!r} before command {later_seg.name!r}",
                )
            if any(key == "arg" for key, _ in later_seg.query_items):
                raise ParseError(
                    f"core arg query on non-command segment {later_seg.name!r}",
                )

        if len(remaining) > 1:
            last_stage = stages[-1]
            if (
                not last_stage.argv_from_query
                and last_stage.metadata.arity == 0
                and last_stage.metadata.parse_mode == "normal"
            ):
                # pipeline_parsing.md §4/§12.1: a metadata-free command may take a
                # multi-segment implied-cat suffix as long as that whole suffix
                # resolves to an existing filesystem path. The discriminator is
                # filesystem resolution, not segment count. A multi-segment suffix
                # that does not resolve is genuine (invalid) metadata-free path
                # args (§13.1/§13.2) and is rejected with 400. A single missing
                # segment instead falls through to the implied cat, which reports
                # the absent resource as 404 (§10.2).
                fs_parts = [
                    percent_decode_segment(r, for_filesystem=True) for r in remaining
                ]
                resolved = resolve_under_root(
                    root,
                    fs_parts,
                    symlink_policy=symlink_policy,
                    case_sensitive=case_sensitive,
                )
                if resolved is None:
                    raise ParseError(
                        f"metadata-free command {last_stage.name} cannot consume path argument segments",
                    )

        break

    input_suffix: list[str] | None = None
    if idx < len(segments):
        input_suffix = segments[idx:]

    if not stages:
        return NotFoundParse()

    if stages and input_suffix is None and method in ("GET", "HEAD"):
        pass

    pipeline = PipelineParse(
        stages=stages,
        input_suffix_raw=input_suffix,
        pipeline_description=_format_pipeline(stages, input_suffix),
        source_path="/".join(input_suffix) if input_suffix else None,
    )
    return pipeline


def check_methods(stages: list[CommandStage], method: str) -> None:
    if method == "HEAD":
        effective = "GET"
    else:
        effective = method
    for stage in stages:
        if not stage.metadata.methods:
            if effective != "GET":
                raise ParseError(
                    f"method {method} not permitted by command {stage.name}",
                    status=405,
                )
            continue
        if effective not in stage.metadata.methods:
            raise ParseError(
                f"method {method} not permitted by command {stage.name}",
                status=405,
            )
