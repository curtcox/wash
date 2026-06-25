"""sdt — tooling for Sequential Directory Trees.

This package currently provides the name-resolution linter (`sdt check`), the
static counterpart to the runtime name resolution defined in runtime.md §6.6.
"""

from sdt.lint import Finding, lint_tree

__all__ = ["Finding", "lint_tree"]
