"""Command-line entry point: ``commerce``."""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from collections.abc import Sequence
from pathlib import Path

import pyarrow.parquet as pq

from commerce_platform import stream as order_stream
from commerce_platform.lakehouse import QualityError, build_bronze, register
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
    b = sub.add_parser("bronze", help="validate landed files and write the bronze layer")
    b.add_argument("--landing", type=Path, default=Path("data/landing"))
    b.add_argument("--lake", type=Path, default=Path("data/lake"))
    b.add_argument("--database", type=Path, default=Path("data/warehouse.duckdb"))
    r = sub.add_parser("replay", help="replay orders from bronze as a stream of order events")
    r.add_argument("--lake", type=Path, default=Path("data/lake"))
    r.add_argument("--batches", type=int, default=1, help="windows to write this run")
    r.add_argument("--window-hours", type=float, default=24.0)
    r.add_argument(
        "--start",
        type=dt.datetime.fromisoformat,
        help="set the watermark first, to rerun or backfill from this time",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.command == "bronze":
        try:
            manifest = build_bronze(args.landing, args.lake)
        except QualityError as exc:
            for problem in exc.problems:
                print(problem)
            print(f"{len(exc.problems)} problem(s); bronze not written")
            return 1
        for name, meta in manifest["tables"].items():
            print(f"{name:<22} {meta['rows']:>9,} rows")
        register(args.lake, args.database)
        print(f"views registered in {args.database}")
        return 0
    if args.command == "replay":
        orders = pq.read_table(args.lake / "bronze" / "orders" / "orders.parquet")
        events = order_stream.order_events(orders)
        done = order_stream.replay(
            events,
            args.lake / "stream" / "order_events",
            window=dt.timedelta(hours=args.window_hours),
            batches=args.batches,
            start=args.start,
        )
        for b in done:
            print(f"{b.start:%Y-%m-%d %H:%M} to {b.end:%Y-%m-%d %H:%M}  {b.rows:>6,} events")
        print(f"watermark {done[-1].end if done else 'unchanged'}")
        return 0
    paths = fetch_all(args.out, args.table)
    for table, path in paths.items():
        print(f"{table:<22} {path}")
    print(ATTRIBUTION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
