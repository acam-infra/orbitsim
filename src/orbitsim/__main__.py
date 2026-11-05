"""CLI entry: ``orbitsim configs/exp_*.yaml``.

Loads a declarative YAML (``name:`` + ``base:`` or inline ``constellation:``
+ ``analysis:``), expands the constellation, runs the declared analyses, and
prints the headline report.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from .constellation import load_constellation
from .report import run


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve(config: dict, here: Path) -> dict:
    """Merge ``base:`` template (scenarios dir) under the experiment config.

    ``base:`` is interpreted relative to the ``exp_*.yaml`` file itself.
    """
    cfg = dict(config)
    base_ref = cfg.pop("base", None)
    if base_ref:
        base_path = (here / base_ref).resolve()
        base = _load_yaml(base_path)
        base.pop("name", None)
        merged = {**base, **cfg}
        return merged
    return cfg


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(args[0])
    config = _resolve(_load_yaml(path), path.parent)
    const = load_constellation(config["constellation"])
    print(run(config, const))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
