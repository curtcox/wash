"""Command metadata loading and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

RECOGNIZED_FIELDS = frozenset(
    {
        "arity",
        "input",
        "output",
        "methods",
        "mime",
        "mutates",
        "parse-mode",
        "stderr",
        "exit",
    }
)

VALID_INPUT = frozenset({"stdin"})
VALID_OUTPUT = frozenset({"stdout"})
VALID_STDERR = frozenset({"discard", "merge"})
VALID_PARSE_MODE = frozenset({"normal", "raw"})
RESERVED_INPUT = frozenset({"file", "none"})
RESERVED_OUTPUT = frozenset({"file"})
RANGE_ARITY_RE = re.compile(r"^\d+\.\.\*?$|^\d+\.\.\d+$")


@dataclass
class ExitMapping:
    explicit: dict[int, int] = field(default_factory=dict)
    wildcard: int | None = None


@dataclass
class CommandMetadata:
    arity: int | Literal["*"] = 0
    input_mode: str = "stdin"
    output_mode: str = "stdout"
    methods: list[str] = field(default_factory=lambda: ["GET"])
    mime: str | None = None
    mutates: bool = False
    parse_mode: str = "normal"
    stderr_mode: str = "discard"
    exit_mapping: ExitMapping = field(default_factory=ExitMapping)
    malformed: bool = False
    malformed_reason: str | None = None

    @property
    def invalid(self) -> bool:
        return self.malformed


def _parse_bool(value: str) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _parse_exit_pairs(tokens: list[str]) -> tuple[ExitMapping | None, str | None]:
    mapping = ExitMapping()
    for token in tokens:
        if "=" not in token:
            return None, f"malformed exit pair: {token!r}"
        code_s, status_s = token.split("=", 1)
        try:
            status = int(status_s)
        except ValueError:
            return None, f"malformed exit status: {status_s!r}"
        if code_s == "*":
            mapping.wildcard = status
        else:
            try:
                code = int(code_s)
            except ValueError:
                return None, f"malformed exit code: {code_s!r}"
            if code < 0:
                return None, f"negative exit code: {code_s!r}"
            mapping.explicit[code] = status
    return mapping, None


def _apply_field(meta: CommandMetadata, name: str, values: list[str]) -> str | None:
    if name == "arity":
        if len(values) != 1:
            return "arity requires exactly one value"
        val = values[0]
        if val == "*":
            meta.arity = "*"
            return None
        if RANGE_ARITY_RE.match(val):
            return f"reserved range arity: {val!r}"
        try:
            n = int(val)
        except ValueError:
            return f"malformed arity: {val!r}"
        if n < 0:
            return f"negative arity: {n}"
        meta.arity = n
        return None

    if name == "input":
        if len(values) != 1:
            return "input requires exactly one value"
        val = values[0]
        if val in RESERVED_INPUT:
            return f"reserved input mode: {val!r}"
        if val not in VALID_INPUT:
            return f"malformed input: {val!r}"
        meta.input_mode = val
        return None

    if name == "output":
        if len(values) != 1:
            return "output requires exactly one value"
        val = values[0]
        if val in RESERVED_OUTPUT:
            return f"reserved output mode: {val!r}"
        if val not in VALID_OUTPUT:
            return f"malformed output: {val!r}"
        meta.output_mode = val
        return None

    if name == "methods":
        if not values:
            return "methods requires at least one value"
        meta.methods = list(values)
        return None

    if name == "mime":
        if len(values) != 1:
            return "mime requires exactly one value"
        val = values[0]
        if "/" not in val or val.strip() != val or not val:
            return f"malformed mime: {val!r}"
        meta.mime = val
        return None

    if name == "mutates":
        if len(values) != 1:
            return "mutates requires exactly one value"
        parsed = _parse_bool(values[0])
        if parsed is None:
            return f"malformed mutates: {values[0]!r}"
        meta.mutates = parsed
        return None

    if name == "parse-mode":
        if len(values) != 1:
            return "parse-mode requires exactly one value"
        val = values[0]
        if val not in VALID_PARSE_MODE:
            return f"malformed parse-mode: {val!r}"
        meta.parse_mode = val
        return None

    if name == "stderr":
        if len(values) != 1:
            return "stderr requires exactly one value"
        val = values[0]
        if val not in VALID_STDERR:
            return f"malformed stderr: {val!r}"
        meta.stderr_mode = val
        return None

    if name == "exit":
        mapping, err = _parse_exit_pairs(values)
        if err:
            return err
        meta.exit_mapping = mapping  # type: ignore[assignment]
        return None

    return None


def load_metadata(root: Path, command_name: str) -> CommandMetadata:
    """Load metadata for a command, applying defaults for missing fields."""
    meta = CommandMetadata()
    meta_path = root / "env" / "meta" / command_name
    if not meta_path.is_file():
        return meta

    fields: dict[str, list[str]] = {}
    try:
        text = meta_path.read_text(encoding="utf-8")
    except OSError:
        meta.malformed = True
        meta.malformed_reason = "failed to read metadata file"
        return meta

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] == "#":
            continue
        parts = stripped.split()
        if not parts:
            continue
        field_name = parts[0]
        if field_name not in RECOGNIZED_FIELDS:
            continue
        fields[field_name] = parts[1:]

    for field_name, values in fields.items():
        err = _apply_field(meta, field_name, values)
        if err:
            meta.malformed = True
            meta.malformed_reason = err
            return meta

    if "GET" in meta.methods and meta.mutates:
        meta.malformed = True
        meta.malformed_reason = "GET permitted with mutates true"
        return meta

    return meta


def default_metadata() -> CommandMetadata:
    return CommandMetadata()


def map_exit_status(meta: CommandMetadata, exit_code: int) -> int:
    if exit_code == 0:
        explicit = meta.exit_mapping.explicit.get(0)
        if explicit is not None:
            return explicit
        return 200
    explicit = meta.exit_mapping.explicit.get(exit_code)
    if explicit is not None:
        return explicit
    if meta.exit_mapping.wildcard is not None:
        return meta.exit_mapping.wildcard
    return 400


def method_permitted(meta: CommandMetadata, method: str) -> bool:
    return method in meta.methods


def head_permitted(meta: CommandMetadata) -> bool:
    # GET permitted => HEAD answered; explicit HEAD in methods also permits it.
    return "GET" in meta.methods or "HEAD" in meta.methods
