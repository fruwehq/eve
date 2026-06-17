"""Console entry point for the ``eve`` CLI (pipx / Homebrew install path).

Thin shim that delegates to ``scripts/eve-cli:main()`` so the CLI tree stays
in ``scripts/`` while the installed package exposes a standard ``eve`` command.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import runpy

    module = runpy.run_path(str(root / "scripts" / "eve-cli"), run_name="__main__")
    return int(module["main"]())


if __name__ == "__main__":
    raise SystemExit(main())
