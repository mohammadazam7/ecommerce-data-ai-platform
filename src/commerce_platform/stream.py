"""Replay Olist orders as a stream of order events, for incremental processing.

The source has one row per order with a timestamp per milestone. Real systems emit those
milestones as separate events over time, and downstream models have to be built to
process them incrementally. This module turns each order into its events (purchased,
approved, shipped, delivered, and canceled or unavailable for orders that ended that
way) and replays them in time order, one window per run.

Replay keeps a watermark: the event time up to which events have been written. Each run
writes the events in the next window to their own Parquet file, named after the window,
then moves the watermark. Re-running a window rewrites the same file with the same
rows, so a retried or repeated run never duplicates events.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

log = logging.getLogger(__name__)

# (event type, orders column holding its time)
MILESTONES: tuple[tuple[str, str], ...] = (
    ("purchased", "order_purchase_timestamp"),
    ("approved", "order_approved_at"),
    ("shipped", "order_delivered_carrier_date"),
    ("delivered", "order_delivered_customer_date"),
)
TERMINAL = {"canceled": "canceled", "unavailable": "unavailable"}
EVENT_SCHEMA = pa.schema(
    [
        pa.field("event_id", pa.string(), nullable=False),
        pa.field("order_id", pa.string(), nullable=False),
        pa.field("event_type", pa.string(), nullable=False),
        pa.field("event_time", pa.timestamp("s"), nullable=False),
    ]
)
WATERMARK = "_watermark.json"


def _event_id(order_id: str, event_type: str) -> str:
    return hashlib.sha1(f"{order_id}|{event_type}".encode()).hexdigest()[:20]


def order_events(orders: pa.Table) -> pa.Table:
    """Every milestone of every order as one event row, sorted by time then order.

    Canceled and unavailable orders get a terminal event at the last milestone they
    reached, because the source records the final status but not when it was set.
    """
    ids: list[str] = []
    kinds: list[str] = []
    times: list[dt.datetime] = []
    rows = orders.select(["order_id", "order_status"] + [c for _, c in MILESTONES]).to_pylist()
    for row in rows:
        last: dt.datetime | None = None
        for kind, column in MILESTONES:
            when = row[column]
            if when is None:
                continue
            if last is not None and when < last:
                # A few source rows record a milestone before the previous one; keep the
                # stream ordered per order rather than invent a time.
                when = last
            ids.append(row["order_id"])
            kinds.append(kind)
            times.append(when)
            last = when
        terminal = TERMINAL.get(row["order_status"])
        if terminal and last is not None:
            ids.append(row["order_id"])
            kinds.append(terminal)
            times.append(last)
    table = pa.table(
        {
            "event_id": [_event_id(o, k) for o, k in zip(ids, kinds, strict=True)],
            "order_id": ids,
            "event_type": kinds,
            "event_time": pa.array(times, type=pa.timestamp("s")),
        },
        schema=EVENT_SCHEMA,
    )
    return table.sort_by([("event_time", "ascending"), ("order_id", "ascending")])


@dataclass(frozen=True, slots=True)
class Batch:
    start: dt.datetime  # exclusive
    end: dt.datetime  # inclusive
    rows: int
    path: Path | None


def read_watermark(stream: Path) -> dt.datetime | None:
    path = stream / WATERMARK
    if not path.exists():
        return None
    return dt.datetime.fromisoformat(json.loads(path.read_text())["event_time"])


def _write_watermark(stream: Path, when: dt.datetime) -> None:
    tmp = stream / (WATERMARK + ".tmp")
    tmp.write_text(json.dumps({"event_time": when.isoformat()}) + "\n")
    os.replace(tmp, stream / WATERMARK)


def replay(
    events: pa.Table,
    stream: Path,
    window: dt.timedelta = dt.timedelta(days=1),
    batches: int = 1,
    start: dt.datetime | None = None,
) -> list[Batch]:
    """Write the next ``batches`` windows of events after the watermark.

    ``start`` sets the watermark explicitly (for a backfill or a rerun); otherwise the
    stored watermark is used, or the instant before the first event on a fresh stream.
    """
    if window <= dt.timedelta(0):
        raise ValueError("window must be positive")
    stream.mkdir(parents=True, exist_ok=True)
    first = events.column("event_time")[0].as_py() if events.num_rows else None
    mark = start or read_watermark(stream) or (first - dt.timedelta(seconds=1) if first else None)
    if mark is None:
        return []
    done: list[Batch] = []
    times = events.column("event_time")
    for _ in range(batches):
        end = mark + window
        mask = pc.and_(
            pc.greater(times, pa.scalar(mark, pa.timestamp("s"))),
            pc.less_equal(times, pa.scalar(end, pa.timestamp("s"))),
        )
        part = events.filter(mask)
        path = None
        if part.num_rows:
            path = stream / f"date={end:%Y-%m-%d}" / f"events_{end:%Y%m%dT%H%M%S}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".parquet.tmp")
            pq.write_table(part, tmp)
            os.replace(tmp, path)
        _write_watermark(stream, end)
        log.info("replayed %s to %s rows=%d", mark, end, part.num_rows)
        done.append(Batch(mark, end, part.num_rows, path))
        mark = end
    return done


def read_stream(stream: Path) -> pa.Table:
    """Every event written so far, as one table."""
    files = sorted(stream.glob("date=*/*.parquet"))
    if not files:
        return EVENT_SCHEMA.empty_table()
    return pa.concat_tables([pq.ParquetFile(f).read().cast(EVENT_SCHEMA) for f in files])
