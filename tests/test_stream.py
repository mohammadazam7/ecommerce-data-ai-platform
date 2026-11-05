import datetime as dt
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pytest

from commerce_platform.stream import (
    EVENT_SCHEMA,
    order_events,
    read_stream,
    read_watermark,
    replay,
)

TS = pa.timestamp("s")


def _ts(s: str | None) -> dt.datetime | None:
    return None if s is None else dt.datetime.fromisoformat(s)


def _orders(
    rows: list[tuple[str, str, str | None, str | None, str | None, str | None]],
) -> pa.Table:
    cols = ["order_purchase_timestamp", "order_approved_at"]
    cols += ["order_delivered_carrier_date", "order_delivered_customer_date"]
    data: dict[str, object] = {
        "order_id": [r[0] for r in rows],
        "order_status": [r[1] for r in rows],
    }
    for i, c in enumerate(cols):
        data[c] = pa.array([_ts(r[2 + i]) for r in rows], type=TS)
    return pa.table(data)


ORDERS = _orders(
    [
        ("o1", "delivered", "2017-01-01 10:00:00", "2017-01-01 11:00:00", "2017-01-02 09:00:00",
         "2017-01-05 15:00:00"),
        ("o2", "canceled", "2017-01-01 12:00:00", "2017-01-01 12:30:00", None, None),
        ("o3", "shipped", "2017-01-03 08:00:00", None, "2017-01-04 10:00:00", None),
        # The source sometimes records a milestone before the previous one; the stream keeps order.
        ("o4", "delivered", "2017-01-02 10:00:00", "2017-01-02 09:00:00", "2017-01-03 10:00:00",
         "2017-01-06 10:00:00"),
    ]
)  # fmt: skip


def test_events_per_order() -> None:
    ev = order_events(ORDERS)
    assert ev.schema == EVENT_SCHEMA
    by_order: dict[str, list[str]] = {}
    for r in ev.to_pylist():
        by_order.setdefault(r["order_id"], []).append(r["event_type"])
    assert by_order["o1"] == ["purchased", "approved", "shipped", "delivered"]
    assert by_order["o2"] == ["purchased", "approved", "canceled"]
    assert by_order["o3"] == ["purchased", "shipped"]
    times = ev.column("event_time").to_pylist()
    assert times == sorted(times)
    assert len(set(ev.column("event_id").to_pylist())) == ev.num_rows


def test_out_of_order_milestone_is_clamped() -> None:
    o4 = order_events(ORDERS).filter(pc.equal(pc.field("order_id"), "o4")).to_pylist()
    assert [r["event_time"] for r in o4] == sorted(r["event_time"] for r in o4)


def test_replay_is_incremental_and_complete(tmp_path: Path) -> None:
    ev = order_events(ORDERS)
    first = replay(ev, tmp_path, batches=2)
    assert [b.rows > 0 for b in first] == [True, True]
    mark = read_watermark(tmp_path)
    assert mark == first[-1].end
    rest = replay(ev, tmp_path, batches=10)
    assert sum(b.rows for b in first + rest) == ev.num_rows
    assert read_stream(tmp_path).num_rows == ev.num_rows


def test_rerunning_a_window_does_not_duplicate(tmp_path: Path) -> None:
    ev = order_events(ORDERS)
    done = replay(ev, tmp_path, batches=10)
    replay(ev, tmp_path, batches=3, start=done[0].start)
    out = read_stream(tmp_path)
    assert out.num_rows == ev.num_rows
    assert len(set(out.column("event_id").to_pylist())) == ev.num_rows


def test_empty_and_invalid(tmp_path: Path) -> None:
    assert replay(EVENT_SCHEMA.empty_table(), tmp_path) == []
    assert read_stream(tmp_path).num_rows == 0
    with pytest.raises(ValueError):
        replay(order_events(ORDERS), tmp_path, window=dt.timedelta(0))
