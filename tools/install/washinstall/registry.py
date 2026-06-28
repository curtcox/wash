"""The bundled command registry (specs/command_install.md §8).

The catalog vendored under ``catalog/`` is the toolbox from ``tools.toml`` (source
of truth) and its generated ``tools.json`` (read here). It is used to resolve
friendly names to host commands, to suggest an install command when one is
missing, and — via the ``meta_hints.toml`` overlay — to supply derivable runtime
metadata.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CATALOG_DIR = Path(__file__).parent / "catalog"
CATALOG_JSON = CATALOG_DIR / "tools.json"
META_HINTS = CATALOG_DIR / "meta_hints.toml"

_PAREN = re.compile(r"\(([^)]*)\)")
_SPLIT = re.compile(r"[\s/,]+")


def _is_real_pkg(value: str | None) -> bool:
    """A usable package name, not a '# do it another way' note (mirrors generate.py)."""
    if not value:
        return False
    return not value.strip().startswith("#")


def _name_tokens(name: str) -> set[str]:
    """Derive lookup tokens from a catalog ``name`` field (§8.2).

    e.g. ``"ripgrep (rg)"`` -> {ripgrep, rg}; ``"xxd / hexdump / od"`` ->
    {xxd, hexdump, od}; ``"miller (mlr)"`` -> {miller, mlr}.
    """
    tokens: set[str] = set()
    for inner in _PAREN.findall(name):
        for tok in _SPLIT.split(inner):
            if tok:
                tokens.add(tok.lower())
    bare = _PAREN.sub("", name)
    for part in bare.split("/"):
        words = part.split()
        if words:
            tokens.add(words[0].lower())
    return tokens


@dataclass
class Entry:
    name: str
    role: str
    group: str
    avail: str
    brew: str | None
    apt: str | None
    when: str
    tokens: set[str] = field(default_factory=set)
    raw: dict = field(default_factory=dict)

    def install_hint(self) -> str | None:
        """Human-readable install suggestion, brew first then apt (§4.1)."""
        parts = []
        if _is_real_pkg(self.brew):
            parts.append(f"brew install {self.brew}")
        if _is_real_pkg(self.apt):
            parts.append(f"sudo apt-get install {self.apt}")
        if parts:
            return "  or  ".join(parts)
        # A note such as "cargo install frawk" lives in the brew/apt field.
        for raw in (self.brew, self.apt):
            if raw:
                return raw.lstrip("# ").strip()
        return None


class Registry:
    def __init__(self, entries: list[Entry]):
        self.entries = entries
        self._by_token: dict[str, Entry] = {}
        for e in entries:
            for tok in e.tokens:
                # First definition of a token wins; later duplicates are ignored.
                self._by_token.setdefault(tok, e)

    def lookup(self, name: str) -> Entry | None:
        """Exact token lookup (§8.2)."""
        return self._by_token.get(name.lower())

    def search(self, query: str) -> list[Entry]:
        """Substring match across name, role, and when, plus exact token (§8.2)."""
        q = query.lower()
        hits: list[Entry] = []
        for e in self.entries:
            if (
                q in e.tokens
                or q in e.name.lower()
                or q in e.role.lower()
                or q in e.when.lower()
            ):
                hits.append(e)
        return hits


def load_registry(path: Path = CATALOG_JSON) -> Registry:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for raw in data:
        name = raw["name"]
        entries.append(
            Entry(
                name=name,
                role=raw.get("role", ""),
                group=raw.get("group", ""),
                avail=raw.get("avail", ""),
                brew=raw.get("brew"),
                apt=raw.get("apt"),
                when=raw.get("when", ""),
                tokens=_name_tokens(name),
                raw=raw,
            )
        )
    return Registry(entries)


def load_meta_hints(path: Path = META_HINTS) -> dict[str, dict[str, str]]:
    """Metadata-hints overlay keyed by command basename (§8.3)."""
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)
    # Each top-level table is one command's hints; coerce values to strings.
    return {
        cmd: {k: str(v) for k, v in fields.items()}
        for cmd, fields in data.items()
        if isinstance(fields, dict)
    }
