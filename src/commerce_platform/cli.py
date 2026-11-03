"""Command-line entry point: ``commerce``."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from commerce_platform.sources import ATTRIBUTION, FILES, fetch_all


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="commerce", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("download", help="download the pinned Olist source files")
    d.add_argument("--out", type=Path, default=Path("data/landing"), help="landing directory")
    d.add_argument(
        "--table",
        action="append",
        choices=[f.table for f in FILES],
        help="download only this table (repeatable); default is every table",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    paths = fetch_all(args.out, args.table)
    for table, path in paths.items():
        print(f"{table:<22} {path}")
    print(ATTRIBUTION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
