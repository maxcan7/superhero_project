"""Check that private (single-underscore) functions and methods have docstrings."""

import ast
import sys
from pathlib import Path


def check_file(path: Path) -> list[str]:
    """Return violation strings for every private def missing a docstring."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        name = node.name
        # single-underscore prefix only; dunders are covered by ruff D105/D107
        if not (name.startswith("_") and not name.startswith("__")):
            continue
        if not (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            violations.append(f"{path}:{node.lineno}: {name} missing docstring")
    return violations


def main() -> int:
    """Run the checker over all files passed as arguments."""
    files = [Path(a) for a in sys.argv[1:]]
    violations: list[str] = []
    for f in files:
        violations.extend(check_file(f))
    for v in violations:
        print(v)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
