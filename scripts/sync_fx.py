#!/usr/bin/env python3
"""Copy scripts/fx/fx.py into each consumer skill as scripts/_fx.py.

Usage:
  python3 scripts/sync_fx.py          # write the copies
  python3 scripts/sync_fx.py --check  # exit 1 if any copy is stale or missing
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "scripts" / "fx" / "fx.py"
CONSUMERS = REPO_ROOT / "scripts" / "fx" / "consumers.txt"


def _banner() -> str:
    spec = importlib.util.spec_from_file_location("_fx_source", SOURCE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.BANNER


def consumers() -> list[str]:
    lines = CONSUMERS.read_text(encoding="utf-8").splitlines()
    return [s.strip() for s in lines if s.strip() and not s.startswith("#")]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = _banner() + SOURCE.read_text(encoding="utf-8")
    stale = []
    for skill in consumers():
        target = REPO_ROOT / "skills" / skill / "scripts" / "_fx.py"
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current == expected:
            continue
        if args.check:
            stale.append(str(target.relative_to(REPO_ROOT)))
        else:
            target.write_text(expected, encoding="utf-8", newline="\n")
            print(f"wrote {target.relative_to(REPO_ROOT)}")
    if stale:
        print("stale _fx.py copies, run python3 scripts/sync_fx.py:", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
